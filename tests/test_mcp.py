"""Servidor MCP: as ferramentas pelo cliente do SDK, no mesmo processo."""

import json
import os
import subprocess
import sys

import pytest
from mcp import Client

from app.db import banco_do_perfil
from app.ia import AguardandoResposta, executar
from app.ia.manual import obter_pedido
from app.ia.tarefas import TESTAR_CONEXAO
from app.mcp.servidor import criar_servidor
from app.perfis.servico import criar_perfil

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def ana(pasta_dados):
    return criar_perfil(pasta_dados, "Ana Exemplo", "ana")


async def _pedido_da_tela(perfil) -> str:
    """Um pedido do modo manual criado como a tela cria."""
    with pytest.raises(AguardandoResposta) as aguardando:
        await executar(perfil, TESTAR_CONEXAO, "Diga ok.", engine=banco_do_perfil(perfil.slug))
    return aguardando.value.pedido.id


def _texto(resultado) -> str:
    return resultado.content[0].text


async def test_lista_as_ferramentas(ana):
    async with Client(criar_servidor("ana")) as cliente:
        nomes = {f.name for f in (await cliente.list_tools()).tools}
    assert {"pedidos_pendentes", "ver_pedido", "responder_pedido"} <= nomes


async def test_responde_pelo_claude_desktop_um_pedido_criado_na_tela(ana):
    pedido_id = await _pedido_da_tela(ana)
    async with Client(criar_servidor("ana")) as cliente:
        assert pedido_id in _texto(await cliente.call_tool("pedidos_pendentes", {}))
        pacote = _texto(await cliente.call_tool("ver_pedido", {"pedido_id": pedido_id}))
        assert "responder_pedido" in pacote and "testar_conexao v1" in pacote

        resposta = {"ok": True, "mensagem": "Conexão ok — ç e ã"}
        resultado = await cliente.call_tool(
            "responder_pedido", {"pedido_id": pedido_id, "resposta": resposta}
        )
    assert not resultado.is_error and "aceita" in _texto(resultado)
    pedido = obter_pedido(banco_do_perfil("ana"), pedido_id)
    assert pedido.status == "respondido" and pedido.respondido_por == "claude_desktop"
    # a tela, rodando de novo, acha a resposta no cache
    saida = await executar(ana, TESTAR_CONEXAO, "Diga ok.", engine=banco_do_perfil("ana"))
    assert saida.mensagem == "Conexão ok — ç e ã"


async def test_resposta_em_texto_ou_com_envelope_tambem_vale(ana):
    pedido_id = await _pedido_da_tela(ana)
    envelope = {"pedido": pedido_id, "resposta": {"ok": True, "mensagem": "ok"}}
    async with Client(criar_servidor("ana")) as cliente:
        resultado = await cliente.call_tool(
            "responder_pedido", {"pedido_id": pedido_id, "resposta": json.dumps(envelope)}
        )
    assert not resultado.is_error


async def test_resposta_invalida_volta_com_o_que_corrigir(ana):
    pedido_id = await _pedido_da_tela(ana)
    async with Client(criar_servidor("ana")) as cliente:
        resultado = await cliente.call_tool(
            "responder_pedido", {"pedido_id": pedido_id, "resposta": {"ok": "talvez"}}
        )
        assert resultado.is_error and "mensagem" in _texto(resultado)
        assert "responder_pedido" in _texto(resultado)
        # o pedido continua esperando: o Claude corrige e tenta de novo
        assert pedido_id in _texto(await cliente.call_tool("pedidos_pendentes", {}))


async def test_pedido_inexistente_e_perfil_inexistente(ana):
    async with Client(criar_servidor("ana")) as cliente:
        resultado = await cliente.call_tool("ver_pedido", {"pedido_id": "P-ZZZZZZ"})
    assert resultado.is_error and "Não existe" in _texto(resultado)
    async with Client(criar_servidor("bia")) as cliente:
        resultado = await cliente.call_tool("pedidos_pendentes", {})
    assert resultado.is_error and "não encontrado" in _texto(resultado)


async def test_sem_perfil_usa_o_ultimo_aberto(ana):
    from app import config

    config.salvar_config(config.carregar_config().model_copy(update={"ultimo_perfil": "ana"}))
    async with Client(criar_servidor()) as cliente:
        resultado = await cliente.call_tool("pedidos_pendentes", {})
    assert not resultado.is_error


def test_processo_real_so_fala_o_protocolo_no_stdout(ana):
    """O Claude Desktop lê o stdout como JSON-RPC: um print qualquer quebra a conexão."""
    pedido = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "teste", "version": "1"},
        },
    }
    processo = subprocess.run(
        [sys.executable, "-m", "app.mcp", "--perfil", "ana"],
        input=json.dumps(pedido) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    linhas = [linha for linha in processo.stdout.splitlines() if linha.strip()]
    assert linhas, processo.stderr
    for linha in linhas:
        assert json.loads(linha)["jsonrpc"] == "2.0"
    assert json.loads(linhas[0])["result"]["serverInfo"]["name"] == "jobfit"
