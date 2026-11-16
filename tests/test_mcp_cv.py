"""Gerar CV pelo Claude Desktop: pedido, resposta, rascunho e checagem, sem contato nem 🔒."""

import re

import pytest
from mcp import Client

from app.cv.servico import obter_cv, rascunho_do_cv, salvar_rascunho
from app.db import banco_do_perfil
from app.dossie.estrutura import inserir_fatos
from app.dossie.formato import escrever_dossie, ler_dossie
from app.dossie.modelos import Fato
from app.dossie.versoes import caminho_dossie
from app.mcp.servidor import criar_servidor
from app.perfis.servico import criar_perfil
from tests.test_cv_servico import EMAIL, REDIGIDO
from tests.test_vagas_servico import SAIDA, VAGA
from tests.test_web_vagas import EXEMPLO

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def ana(pasta_dados):
    perfil = criar_perfil(pasta_dados, "Ana Exemplo", "ana")
    doc = ler_dossie(EXEMPLO)
    inserir_fatos(doc, [Fato(id="F-800", tipo="contato", texto=f"E-mail: {EMAIL}")])
    caminho_dossie(pasta_dados, "ana").write_text(escrever_dossie(doc), encoding="utf-8")
    return perfil


def _texto(resultado) -> str:
    return resultado.content[0].text


def _pedido(texto: str) -> str:
    return re.search(r"P-[A-Z0-9]{6}", texto).group(0)


async def _responder(mcp, ferramenta: str, argumentos: dict, saida: dict) -> str:
    """Chama a ferramenta, responde o pedido que ela devolver e chama de novo."""
    pedido = _texto(await mcp.call_tool(ferramenta, argumentos))
    aceita = await mcp.call_tool(
        "responder_pedido", {"pedido_id": _pedido(pedido), "resposta": saida}
    )
    assert not aceita.is_error, _texto(aceita)
    return pedido


async def test_gerar_cv_pelo_mcp(ana):
    async with Client(criar_servidor("ana")) as mcp:
        await _responder(mcp, "avaliar_vaga", {"vaga": VAGA}, SAIDA)
        pedido = await _responder(mcp, "gerar_cv", {"vaga_id": 1}, REDIGIDO)
        resultado = _texto(await mcp.call_tool("gerar_cv", {"vaga_id": 1}))

    assert 'gerar_cv(vaga_id=1, idioma="pt")' in pedido and "redigir_cv v1" in pedido
    for texto in (pedido, resultado):
        assert EMAIL not in texto  # contato não vai para o Claude
        assert "Faixa salarial mínima" not in texto  # 🔒
    assert "Rascunho do CV em português (cv_id=1)" in resultado
    assert "Título: Gerente de Dados e IA" in resultado
    assert "Reduziu de 5 para 2 dias o fechamento." in resultado
    assert "não achou bloqueios" in resultado
    assert "http://127.0.0.1:8765/p/ana/cvs/1" in resultado
    assert rascunho_do_cv(obter_cv(banco_do_perfil("ana"), 1)).experiencias[1].bullets[0].fatos == [
        "F-021"
    ]  # o ID inventado (F-999) saiu, como na tela


async def test_reabre_o_rascunho_editado_e_mostra_o_bloqueio(ana):
    async with Client(criar_servidor("ana")) as mcp:
        await _responder(mcp, "avaliar_vaga", {"vaga": VAGA}, SAIDA)
        await _responder(mcp, "gerar_cv", {"vaga_id": 1}, REDIGIDO)
        await mcp.call_tool("gerar_cv", {"vaga_id": 1})  # cria o rascunho a partir do cache
        engine = banco_do_perfil("ana")
        rascunho = rascunho_do_cv(obter_cv(engine, 1))
        rascunho.experiencias[0].bullets[0].texto = "Automatizou 95% das leituras."
        salvar_rascunho(engine, 1, rascunho)
        resultado = _texto(await mcp.call_tool("gerar_cv", {"vaga_id": 1}))
    assert "Automatizou 95% das leituras." in resultado
    assert "bloqueia o PDF por 1 problema" in resultado
    assert "(bloqueia) Automatizou 95% das leituras.:" in resultado


async def test_idioma_invalido_e_vaga_inexistente(ana):
    async with Client(criar_servidor("ana")) as mcp:
        await _responder(mcp, "avaliar_vaga", {"vaga": VAGA}, SAIDA)
        idioma = await mcp.call_tool("gerar_cv", {"vaga_id": 1, "idioma": "es"})
        inexistente = await mcp.call_tool("gerar_cv", {"vaga_id": 7})
    assert idioma.is_error and '"pt" ou "en"' in _texto(idioma)
    assert inexistente.is_error and "Não existe a vaga 7" in _texto(inexistente)
