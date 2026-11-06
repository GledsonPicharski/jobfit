"""Avaliar vaga pelo Claude Desktop dá o mesmo que pela tela, no modo manual."""

import json
import re
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from app.db import banco_do_perfil
from app.dossie.versoes import caminho_dossie
from app.main import create_app
from app.mcp.servidor import criar_servidor
from app.perfis.modelos import ConfigIA
from app.perfis.servico import criar_perfil, salvar_perfil
from app.vagas import servico
from tests.ia_falsa import Falso
from tests.test_vagas_servico import SAIDA, VAGA
from tests.test_web_vagas import EXEMPLO, ORIGEM

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _perfil(pasta, slug):
    perfil = criar_perfil(pasta, slug.title(), slug)
    caminho_dossie(pasta, slug).write_text(EXEMPLO, encoding="utf-8")
    return perfil


def _texto(resultado) -> str:
    return resultado.content[0].text


def _pedido(texto: str) -> str:
    return re.search(r"P-[A-Z0-9]{6}", texto).group(0)


async def test_mesma_vaga_e_mesma_resposta_dao_a_mesma_nota_na_tela_e_no_mcp(pasta_dados):
    _perfil(pasta_dados, "ana")
    _perfil(pasta_dados, "bia")

    # pela tela, no perfil da Ana
    cliente = TestClient(create_app(), base_url=ORIGEM, headers={"Origin": ORIGEM})
    cliente.post("/p/ana/vagas", data={"entrada": VAGA})
    destino = cliente.get("/p/ana/vagas/1/avaliar", follow_redirects=False).headers["location"]
    pedido_tela = urlsplit(destino).path.rsplit("/", 1)[1]
    colado = json.dumps({"pedido": pedido_tela, "resposta": SAIDA}, ensure_ascii=False)
    cliente.post(f"/p/ana/pedidos/{pedido_tela}/resposta", data={"resposta": colado})
    cliente.get("/p/ana/vagas/1/avaliar")
    pela_tela = servico.ultima_avaliacao(banco_do_perfil("ana"), 1)

    # pelo Claude Desktop, no perfil da Bia
    async with Client(criar_servidor("bia")) as mcp:
        pedido = _texto(await mcp.call_tool("avaliar_vaga", {"vaga": VAGA}))
        assert "avaliar_vaga(vaga_id=1)" in pedido and "Faixa salarial mínima" not in pedido
        aceita = await mcp.call_tool(
            "responder_pedido", {"pedido_id": _pedido(pedido), "resposta": SAIDA}
        )
        assert not aceita.is_error
        resultado = _texto(await mcp.call_tool("avaliar_vaga", {"vaga_id": 1}))
    pelo_mcp = servico.ultima_avaliacao(banco_do_perfil("bia"), 1)

    assert (pelo_mcp.nota, pelo_mcp.faixa) == (pela_tela.nota, pela_tela.faixa) == (80, "B")
    assert pelo_mcp.requisitos == pela_tela.requisitos
    assert "B · combina bem · 80/100" in resultado
    assert "Forças:" in resultado and "Lacunas:" in resultado
    assert "http://127.0.0.1:8765/p/bia/vagas/1" in resultado
    assert "modo API" not in resultado


async def test_pedido_da_tela_respondido_pelo_mcp_segue_na_tela(pasta_dados):
    _perfil(pasta_dados, "ana")
    cliente = TestClient(create_app(), base_url=ORIGEM, headers={"Origin": ORIGEM})
    cliente.post("/p/ana/vagas", data={"entrada": VAGA})
    destino = cliente.get("/p/ana/vagas/1/avaliar", follow_redirects=False).headers["location"]
    pedido_id = urlsplit(destino).path.rsplit("/", 1)[1]

    async with Client(criar_servidor("ana")) as mcp:
        await mcp.call_tool("responder_pedido", {"pedido_id": pedido_id, "resposta": SAIDA})
    cliente.get("/p/ana/vagas/1/avaliar")
    assert '<span class="faixa faixa-B">B</span> 80' in cliente.get("/p/ana/vagas/1").text


async def test_vaga_repetida_reaproveita_e_lista_mostra_a_nota(pasta_dados):
    _perfil(pasta_dados, "ana")
    async with Client(criar_servidor("ana")) as mcp:
        pedido = _texto(await mcp.call_tool("avaliar_vaga", {"vaga": VAGA}))
        await mcp.call_tool("responder_pedido", {"pedido_id": _pedido(pedido), "resposta": SAIDA})
        de_novo = _texto(await mcp.call_tool("avaliar_vaga", {"vaga": VAGA}))
        lista = _texto(await mcp.call_tool("listar_vagas", {}))
    assert "Vaga 1:" in de_novo and "80/100" in de_novo
    assert "vaga_id=1: Gerente de Dados Sênior" in lista and "B (combina bem, 80/100)" in lista


async def test_entrada_vazia_vaga_inexistente_e_linkedin(pasta_dados):
    _perfil(pasta_dados, "ana")
    async with Client(criar_servidor("ana")) as mcp:
        vazia = await mcp.call_tool("avaliar_vaga", {})
        inexistente = await mcp.call_tool("avaliar_vaga", {"vaga_id": 9})
        linkedin = await mcp.call_tool(
            "avaliar_vaga", {"vaga": "https://www.linkedin.com/jobs/view/123"}
        )
    assert vazia.is_error and "URL ou o texto" in _texto(vazia)
    assert inexistente.is_error and "Não existe a vaga 9" in _texto(inexistente)
    assert linkedin.is_error and "LinkedIn" in _texto(linkedin)


async def test_no_modo_api_avalia_direto_e_avisa_o_custo(pasta_dados, usar_modelo):
    perfil = _perfil(pasta_dados, "ana")
    salvar_perfil(
        pasta_dados, perfil.model_copy(update={"ia": ConfigIA().com_provedor("anthropic")})
    )
    usar_modelo(Falso(SAIDA))
    async with Client(criar_servidor("ana")) as mcp:
        resultado = _texto(await mcp.call_tool("avaliar_vaga", {"vaga": VAGA}))
    assert "80/100" in resultado and "modo API" in resultado
