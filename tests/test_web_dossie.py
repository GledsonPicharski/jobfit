from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import banco_do_perfil
from app.dossie.formato import ler_dossie
from app.dossie.versoes import caminho_dossie, versoes
from app.main import create_app
from app.perfis.servico import criar_perfil

ORIGEM = "http://127.0.0.1:8765"
RAIZ = Path(__file__).resolve().parents[1]
EXEMPLO = (RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md").read_text(encoding="utf-8")


@pytest.fixture
def cliente():
    return TestClient(create_app(), base_url=ORIGEM, headers={"Origin": ORIGEM})


@pytest.fixture
def ana(pasta_dados):
    return criar_perfil(pasta_dados, "Ana Exemplo", "ana")


@pytest.fixture
def ana_com_dossie(ana, pasta_dados):
    caminho_dossie(pasta_dados, "ana").write_text(EXEMPLO, encoding="utf-8")
    return ana


def _arquivo(pasta_dados) -> str:
    return caminho_dossie(pasta_dados, "ana").read_text(encoding="utf-8")


def test_menu_tem_dossie(cliente, ana):
    assert 'href="/p/ana/dossie"' in cliente.get("/p/ana").text


def test_primeira_visita_cria_o_dossie(cliente, ana, pasta_dados):
    tela = cliente.get("/p/ana/dossie")
    assert tela.status_code == 200
    assert "versão 1" in tela.text
    assert "Experiências" in tela.text
    assert "dossie.md" in tela.text  # mostra onde editar à mão
    assert "Ana Exemplo" in _arquivo(pasta_dados)


def test_mostra_secoes_e_fatos(cliente, ana_com_dossie):
    tela = cliente.get("/p/ana/dossie").text
    assert "versão 3" in tela
    assert "Empresa Exemplo" in tela
    assert "Lançou o Leitor Automático" in tela
    assert 'id="F-014"' in tela
    assert "2023-03 – atual" in tela
    assert "🔒" in tela


def test_visao_de_cv_esconde_privado(cliente, ana_com_dossie):
    tela = cliente.get("/p/ana/dossie?visao=cv").text
    assert "Prefere trabalho remoto" in tela
    assert "Faixa salarial mínima" not in tela  # F-002 é 🔒


def test_alternar_privado_grava_versao_e_some_da_visao_de_cv(cliente, ana_com_dossie, pasta_dados):
    resposta = cliente.post(
        "/p/ana/dossie/fatos/F-001/alternar", data={"campo": "privado"}, follow_redirects=False
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/p/ana/dossie#F-001"

    doc = ler_dossie(_arquivo(pasta_dados))
    assert doc.fato("F-001").privado is True
    assert doc.metadados["versao"] == 4
    assert versoes(banco_do_perfil("ana"))[0].motivo == "edicao_app"
    assert "Prefere trabalho remoto" not in cliente.get("/p/ana/dossie?visao=cv").text

    cliente.post("/p/ana/dossie/fatos/F-001/alternar", data={"campo": "privado"})
    assert ler_dossie(_arquivo(pasta_dados)).fato("F-001").privado is False


def test_alternar_nao_enviar_ia(cliente, ana_com_dossie, pasta_dados):
    cliente.post("/p/ana/dossie/fatos/F-010/alternar", data={"campo": "nao_enviar_ia"})
    assert ler_dossie(_arquivo(pasta_dados)).fato("F-010").nao_enviar_ia is True


def test_alternar_campo_desconhecido_ou_fato_inexistente(cliente, ana_com_dossie, pasta_dados):
    url = "/p/ana/dossie/fatos/F-001/alternar"
    assert cliente.post(url, data={"campo": "status"}).status_code == 422
    resposta = cliente.post("/p/ana/dossie/fatos/F-999/alternar", data={"campo": "privado"})
    assert resposta.status_code == 404
    assert _arquivo(pasta_dados) == EXEMPLO


def test_dossie_quebrado_mostra_a_linha_e_nao_grava(cliente, ana_com_dossie, pasta_dados):
    quebrado = EXEMPLO.replace(
        "  tipo: preferencia\n  texto: Prefere", "  tipo: [\n  texto: Prefere"
    )
    caminho_dossie(pasta_dados, "ana").write_text(quebrado, encoding="utf-8")

    tela = cliente.get("/p/ana/dossie")
    assert tela.status_code == 200
    assert "Linha " in tela.text
    assert "/alternar" not in tela.text

    resposta = cliente.post("/p/ana/dossie/fatos/F-001/alternar", data={"campo": "privado"})
    assert resposta.status_code == 409
    assert "Linha " in resposta.text
    assert _arquivo(pasta_dados) == quebrado


def test_historico_e_diff_da_versao(cliente, ana_com_dossie):
    cliente.post("/p/ana/dossie/fatos/F-001/alternar", data={"campo": "privado"})

    lista = cliente.get("/p/ana/dossie/historico").text
    assert "Versão 4" in lista
    assert "edição no app" in lista
    assert "edição manual" in lista
    assert 'href="/p/ana/dossie/historico/4"' in lista

    versao = cliente.get("/p/ana/dossie/historico/4").text
    assert "F-001" in versao
    assert "-  privado: false" in versao or "+  privado: true" in versao


def test_versao_inexistente_da_404(cliente, ana_com_dossie):
    cliente.get("/p/ana/dossie")
    assert cliente.get("/p/ana/dossie/historico/99").status_code == 404
