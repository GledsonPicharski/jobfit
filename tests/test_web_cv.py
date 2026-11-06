import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.cv.servico import obter_cv, rascunho_do_cv
from app.db import banco_do_perfil
from app.dossie.formato import ler_dossie
from app.dossie.versoes import caminho_dossie
from app.main import create_app
from app.perfis.modelos import ConfigIA
from app.perfis.servico import criar_perfil, salvar_perfil
from tests.ia_falsa import Falso
from tests.test_cv_servico import REDIGIDO
from tests.test_vagas_servico import SAIDA, VAGA

ORIGEM = "http://127.0.0.1:8765"
RAIZ = Path(__file__).resolve().parents[1]
EXEMPLO = (RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md").read_text(encoding="utf-8")


class FalsoPorTarefa(Falso):
    """Responde a avaliação e a redação do CV, cada uma com a sua saída."""

    def __call__(self, mensagens, info):
        nome = info.output_tools[0].parameters_json_schema.get("title", "")
        self.respostas = [REDIGIDO if nome == "CVRedigido" else SAIDA]
        return super().__call__(mensagens, info)


@pytest.fixture
def cliente():
    return TestClient(create_app(), base_url=ORIGEM, headers={"Origin": ORIGEM})


@pytest.fixture
def ana(pasta_dados):
    perfil = criar_perfil(pasta_dados, "Ana Exemplo", "ana")
    caminho_dossie(pasta_dados, "ana").write_text(EXEMPLO, encoding="utf-8")
    return perfil


@pytest.fixture
def ana_api(ana, pasta_dados):
    perfil = ana.model_copy(update={"ia": ConfigIA().com_provedor("anthropic")})
    salvar_perfil(pasta_dados, perfil)
    return perfil


def _vaga_avaliada(cliente):
    cliente.post("/p/ana/vagas", data={"entrada": VAGA})
    cliente.get("/p/ana/vagas/1/avaliar")


def _cv(cliente, idioma="pt"):
    return cliente.get(f"/p/ana/vagas/1/cv?idioma={idioma}", follow_redirects=False)


def _rascunho():
    return rascunho_do_cv(obter_cv(banco_do_perfil("ana"), 1))


def test_vaga_avaliada_oferece_gerar_cv(cliente, ana_api, usar_modelo):
    usar_modelo(FalsoPorTarefa())
    _vaga_avaliada(cliente)
    tela = cliente.get("/p/ana/vagas/1").text
    assert 'href="/p/ana/vagas/1/cv?idioma=pt"' in tela
    assert 'href="/p/ana/vagas/1/cv?idioma=en"' in tela


def test_gerar_cv_abre_o_rascunho_conferido(cliente, ana_api, usar_modelo):
    falso = usar_modelo(FalsoPorTarefa())
    _vaga_avaliada(cliente)
    resposta = _cv(cliente)
    assert resposta.headers["location"] == "/p/ana/cvs/1"
    tela = cliente.get("/p/ana/cvs/1").text
    assert "Tudo conferido com o dossiê." in tela
    assert "Ana Exemplo" in tela
    assert 'value="Gerente de Dados e IA"' in tela
    assert "Empresa Exemplo · mar 2023 – atual" in tela
    assert "Automatizou mais de 80% das leituras." in tela
    assert '<button type="submit" name="acao" value="pdf" >' in tela  # habilitado
    assert 'href="/p/ana/cvs/1"' in cliente.get("/p/ana/vagas/1").text
    assert falso.chamadas == 2  # avaliação e redação


def test_numero_falso_bloqueia_o_pdf(cliente, ana_api, usar_modelo):
    usar_modelo(FalsoPorTarefa())
    _vaga_avaliada(cliente)
    _cv(cliente)
    cliente.post(
        "/p/ana/cvs/1",
        data={"experiencias.0.bullets.0": "Automatizou 95% das leituras.", "acao": "salvar"},
    )
    tela = cliente.get("/p/ana/cvs/1").text
    assert "1 ponto(s) a corrigir antes do PDF." in tela
    assert "⛔ Número sem fato de origem: 95%." in tela
    assert 'value="pdf" disabled' in tela


def test_cargo_trocado_e_usar_o_do_dossie(cliente, ana_api, usar_modelo):
    usar_modelo(FalsoPorTarefa())
    _vaga_avaliada(cliente)
    _cv(cliente)
    cliente.post("/p/ana/cvs/1", data={"experiencias.0.titulo": "Head de Dados e IA"})
    tela = cliente.get("/p/ana/cvs/1").text
    assert "Cargo diferente do dossiê (Gerente de Dados e IA)." in tela
    assert 'value="cargo_dossie:0"' in tela
    assert "cargo_confirmar" not in tela  # só no CV em inglês

    cliente.post("/p/ana/cvs/1", data={"acao": "cargo_dossie:0"})
    assert _rascunho().experiencias[0].titulo == "Gerente de Dados e IA"


def test_remover_e_apagar_frase(cliente, ana_api, usar_modelo):
    usar_modelo(FalsoPorTarefa())
    _vaga_avaliada(cliente)
    _cv(cliente)
    cliente.post(
        "/p/ana/cvs/1",
        data={"remover": ["competencias.0"], "resumo.0": "   "},
    )
    rascunho = _rascunho()
    assert rascunho.competencias == [] and rascunho.resumo == []


def test_cv_em_ingles_confirma_a_traducao_do_cargo(cliente, ana_api, pasta_dados, usar_modelo):
    usar_modelo(FalsoPorTarefa())
    _vaga_avaliada(cliente)
    assert _cv(cliente, "en").headers["location"] == "/p/ana/cvs/1"
    tela = cliente.get("/p/ana/cvs/1").text
    assert "Tradução do cargo pela IA" in tela
    assert 'value="cargo_confirmar:0"' in tela

    cliente.post("/p/ana/cvs/1", data={"acao": "cargo_confirmar:0"})
    doc = ler_dossie(caminho_dossie(pasta_dados, "ana").read_text(encoding="utf-8"))
    assert doc.fato("F-010").model_extra["cargo_en"] == "Data & AI Manager"
    assert (
        "Tradução do cargo pela IA: confirme"
        not in cliente.get("/p/ana/cvs/1")
        .text.split("Experience")[1]
        .split("Senior Data Analyst")[0]
    )


def test_modo_manual_volta_para_o_cv(cliente, ana, usar_modelo):
    cliente.post("/p/ana/vagas", data={"entrada": VAGA})
    destino = urlsplit(
        cliente.get("/p/ana/vagas/1/avaliar", follow_redirects=False).headers["location"]
    )
    pedido = destino.path.rsplit("/", 1)[1]
    colado = json.dumps({"pedido": pedido, "resposta": SAIDA}, ensure_ascii=False)
    cliente.post(
        f"/p/ana/pedidos/{pedido}/resposta",
        data={"resposta": colado, "voltar": "/p/ana/vagas/1/avaliar"},
    )

    resposta = _cv(cliente)
    destino = urlsplit(resposta.headers["location"])
    assert parse_qs(destino.query)["voltar"] == ["/p/ana/vagas/1/cv?idioma=pt"]
    pedido = destino.path.rsplit("/", 1)[1]
    pacote = cliente.get(f"/p/ana/pedidos/{pedido}").text
    assert "redigir_cv v1" in pacote
    colado = json.dumps({"pedido": pedido, "resposta": REDIGIDO}, ensure_ascii=False)
    voltou = cliente.post(
        f"/p/ana/pedidos/{pedido}/resposta",
        data={"resposta": colado, "voltar": "/p/ana/vagas/1/cv?idioma=pt"},
        follow_redirects=False,
    )
    assert voltou.headers["location"] == "/p/ana/vagas/1/cv?idioma=pt"
    assert _cv(cliente).headers["location"] == "/p/ana/cvs/1"


def test_cv_inexistente(cliente, ana):
    assert cliente.get("/p/ana/cvs/9").status_code == 404
    assert cliente.get("/p/ana/vagas/9/cv").status_code == 404
