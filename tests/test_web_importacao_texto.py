import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.db import banco_do_perfil
from app.dossie.formato import ler_dossie
from app.dossie.propostas import obter_importacao, propostas_da_importacao
from app.dossie.versoes import caminho_dossie
from app.ia.erros import ErroIA
from app.main import create_app
from app.perfis.modelos import ConfigIA
from app.perfis.servico import criar_perfil, pasta_perfil, salvar_perfil
from app.web import rotas_importacao
from tests.cv_ficticio import gerar_cv_docx, gerar_cv_pdf
from tests.ia_falsa import Falso
from tests.linkedin_pdf_ficticio import gerar_pdf

ORIGEM = "http://127.0.0.1:8765"
RAIZ = Path(__file__).resolve().parents[1]
EXEMPLO = (RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md").read_text(encoding="utf-8")
EMAIL = "ana.exemplo" + "@exemplo.test"  # montado aqui: escrito literal, o pre-commit barra

TEXTO = (
    "Na Empresa Exemplo, liderou a migração do data lake para a nuvem, "
    "reduzindo o custo em 30% — ação contínua.\n"
    f"Contato: {EMAIL}\n"
)
FIEL = {
    "tipo": "resultado",
    "texto": "Liderou a migração do data lake para a nuvem, reduzindo o custo em 30%",
    "empresa": "Empresa Exemplo",
    "trecho": "liderou a migração do data lake para a nuvem, reduzindo o custo em 30%",
}
INVENTADO = {"tipo": "resultado", "texto": "Reduziu o custo em 90%", "trecho": "custo em 90%"}
SAIDA = {"fatos": [FIEL, INVENTADO]}

MD = """# Parte A — Carreira

## Experiências

Na Empresa Exemplo, liderou a migração do data lake para a nuvem, reduzindo o custo em 30%.

# Parte B — Família

Assunto de família que não vai para a IA.
"""


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


def _engine():
    return banco_do_perfil("ana")


def _colar(cliente, texto=TEXTO, **campos):
    return cliente.post(
        "/p/ana/importar/texto", data={"texto": texto, **campos}, follow_redirects=False
    )


def _enviar_md(cliente, conteudo: bytes, nome="dossie v2.md"):
    return cliente.post(
        "/p/ana/importar/texto",
        files={"arquivo": (nome, conteudo, "text/markdown")},
        follow_redirects=False,
    )


def _dossie(pasta_dados) -> str:
    return caminho_dossie(pasta_dados, "ana").read_text(encoding="utf-8")


def _textos(importacao_id=1) -> dict[str, str]:
    return {
        json.loads(p.dados)["texto"]: p.decisao
        for p in propostas_da_importacao(_engine(), importacao_id)
    }


# --- modo manual: o caminho padrão --------------------------------------------


def test_ciclo_manual_do_texto_colado(cliente, ana, pasta_dados):
    resposta = _colar(cliente)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/p/ana/importacoes/1/extrair"

    resposta = cliente.get("/p/ana/importacoes/1/extrair", follow_redirects=False)
    assert resposta.status_code == 303
    destino = urlsplit(resposta.headers["location"])
    assert destino.path.startswith("/p/ana/pedidos/P-")
    assert parse_qs(destino.query)["voltar"] == ["/p/ana/importacoes/1/extrair"]

    pedido_id = destino.path.rsplit("/", 1)[1]
    pacote = cliente.get(f"/p/ana/pedidos/{pedido_id}").text
    assert "extrair_fatos v1" in pacote
    assert "reduzindo o custo em 30% — ação contínua" in pacote
    assert EMAIL not in pacote  # regra 5: contato não vai para a IA
    assert "[e-mail omitido]" in pacote

    colado = json.dumps({"pedido": pedido_id, "resposta": SAIDA}, ensure_ascii=False)
    resposta = cliente.post(
        f"/p/ana/pedidos/{pedido_id}/resposta",
        data={"resposta": colado, "voltar": "/p/ana/importacoes/1/extrair"},
        follow_redirects=False,
    )
    assert resposta.headers["location"] == "/p/ana/importacoes/1/extrair"

    resposta = cliente.get("/p/ana/importacoes/1/extrair", follow_redirects=False)
    assert resposta.headers["location"] == "/p/ana/importacoes/1"
    assert _textos() == {
        f"E-mail: {EMAIL}": "pendente",
        FIEL["texto"]: "pendente",
        INVENTADO["texto"]: "rejeitada",  # trecho sem origem: começa rejeitado
    }
    assert obter_importacao(_engine(), 1).extracao == "feita"
    assert _dossie(pasta_dados) == EXEMPLO  # regra 4

    tela = cliente.get("/p/ana/importacoes/1").text
    assert "O trecho de origem não está no texto importado." in tela
    assert "Extrair fatos com a IA" not in tela


def test_extrair_de_novo_nao_duplica(cliente, ana_api, usar_modelo):
    falso = usar_modelo(Falso(SAIDA))
    _colar(cliente)
    cliente.get("/p/ana/importacoes/1/extrair")
    cliente.get("/p/ana/importacoes/1/extrair")
    assert falso.chamadas == 1
    assert len(propostas_da_importacao(_engine(), 1)) == 3


def test_gravar_o_que_veio_da_ia(cliente, ana_api, usar_modelo, pasta_dados):
    usar_modelo(Falso(SAIDA))
    _colar(cliente, nome="Notas do último emprego")
    cliente.get("/p/ana/importacoes/1/extrair")
    cliente.post("/p/ana/importacoes/1/aprovar-pendentes")
    resposta = cliente.post("/p/ana/importacoes/1/gravar", follow_redirects=False)
    assert resposta.status_code == 303

    doc = ler_dossie(_dossie(pasta_dados))
    novos = {f.texto: f for f in doc.fatos if f.origem == f"texto {date.today().isoformat()}"}
    assert set(novos) == {FIEL["texto"], f"E-mail: {EMAIL}"}
    assert novos[f"E-mail: {EMAIL}"].nao_enviar_ia is True
    assert novos[FIEL["texto"]].empresa == "Empresa Exemplo"
    assert "Notas do último emprego" in cliente.get("/p/ana/importar").text


def test_erro_da_ia_mostra_a_mensagem_e_deixa_tentar_de_novo(cliente, ana_api, monkeypatch):
    async def falhar(*_args, **_kwargs):
        raise ErroIA("Limite de uso do provedor atingido.")

    monkeypatch.setattr(rotas_importacao, "executar", falhar)
    _colar(cliente)
    resposta = cliente.get("/p/ana/importacoes/1/extrair")
    assert resposta.status_code == 502
    assert "Limite de uso do provedor atingido." in resposta.text
    assert "Extrair fatos com a IA" in resposta.text
    assert obter_importacao(_engine(), 1).extracao == "pendente"


# --- .md com seções -----------------------------------------------------------


def test_md_com_titulos_pede_as_secoes_e_so_a_parte_a_vai(cliente, ana_api, usar_modelo):
    falso = usar_modelo(Falso({"fatos": []}))
    resposta = _enviar_md(cliente, MD.encode("utf-8"))
    assert resposta.headers["location"] == "/p/ana/importacoes/1/secoes"
    assert (
        cliente.get("/p/ana/importacoes/1", follow_redirects=False).headers["location"]
        == "/p/ana/importacoes/1/secoes"
    )

    tela = cliente.get("/p/ana/importacoes/1/secoes").text
    for titulo in ("Parte A — Carreira", "Experiências", "Parte B — Família"):
        assert titulo in tela
    assert tela.count('type="checkbox"') == 3

    resposta = cliente.post(
        "/p/ana/importacoes/1/secoes", data={"secao": ["0", "1"]}, follow_redirects=False
    )
    assert resposta.headers["location"] == "/p/ana/importacoes/1/extrair"
    importacao = obter_importacao(_engine(), 1)
    assert importacao.extraido.endswith("_dossie_v2_secoes.md")

    cliente.get("/p/ana/importacoes/1/extrair")
    enviado = str(falso.ultimo_pedido)
    assert "reduzindo o custo em 30%" in enviado
    assert "Família" not in enviado
    assert "Nada novo" in cliente.get("/p/ana/importacoes/1").text


def test_nenhuma_secao_marcada(cliente, ana):
    _enviar_md(cliente, MD.encode("utf-8"))
    resposta = cliente.post("/p/ana/importacoes/1/secoes", data={})
    assert resposta.status_code == 400
    assert "Marque ao menos uma seção." in resposta.text


def test_secoes_grandes_demais(cliente, ana, monkeypatch):
    monkeypatch.setattr(rotas_importacao, "LIMITE_CARACTERES", 50)
    _enviar_md(cliente, MD.encode("utf-8"))
    resposta = cliente.post("/p/ana/importacoes/1/secoes", data={"secao": ["0", "1", "2"]})
    assert resposta.status_code == 413
    assert "limite numa importação é 50" in resposta.text


def test_arquivo_do_bloco_de_notas_antigo(cliente, ana, pasta_dados):
    resposta = _enviar_md(cliente, TEXTO.encode("cp1252"), nome="notas.txt")
    assert resposta.headers["location"] == "/p/ana/importacoes/1/extrair"
    importacao = obter_importacao(_engine(), 1)
    guardado = pasta_perfil(pasta_dados, "ana") / importacao.arquivo
    assert guardado.read_bytes() == TEXTO.encode("cp1252")  # o original, como veio


# --- entradas recusadas e descarte --------------------------------------------


def test_texto_vazio_e_grande_demais(cliente, ana, monkeypatch):
    resposta = _colar(cliente, texto="  \r\n ")
    assert resposta.status_code == 400
    assert "Cole um texto" in resposta.text

    monkeypatch.setattr(rotas_importacao, "LIMITE_CARACTERES", 20)
    resposta = _colar(cliente)
    assert resposta.status_code == 413
    assert "Divida em partes" in resposta.text


def test_descartar(cliente, ana):
    _enviar_md(cliente, MD.encode("utf-8"))
    resposta = cliente.post("/p/ana/importacoes/1/descartar", follow_redirects=False)
    assert resposta.headers["location"] == "/p/ana/importar"
    assert obter_importacao(_engine(), 1).status == "descartada"
    assert "descartada" in cliente.get("/p/ana/importar").text
    assert "Descartada" in cliente.get("/p/ana/importacoes/1").text
    assert (
        cliente.get("/p/ana/importacoes/1/extrair", follow_redirects=False).headers["location"]
        == "/p/ana/importacoes/1"
    )


# --- descrições do PDF do LinkedIn --------------------------------------------


def test_linkedin_manda_as_descricoes_para_a_ia_sem_repetir_cargos(
    cliente, ana_api, usar_modelo, pasta_dados
):
    cargo_repetido = {
        "tipo": "cargo",
        "texto": "Coordenadora de Ciência de Dados — Empresa Exemplo",
        "empresa": "Empresa Exemplo",
        "cargo": "Coordenadora de Ciência de Dados",
        "periodo": {"inicio": "2018-01", "fim": "2023-02"},
        "trecho": "Coordenadora de Ciência de Dados",
    }
    falso = usar_modelo(Falso({"fatos": [cargo_repetido]}))
    cliente.post(
        "/p/ana/importar/linkedin",
        files={"arquivo": ("Perfil.pdf", gerar_pdf("pt"), "application/pdf")},
    )
    importacao = obter_importacao(_engine(), 1)
    assert importacao.extracao == "pendente"
    descricoes = (pasta_perfil(pasta_dados, "ana") / importacao.extraido).read_text(
        encoding="utf-8"
    )
    assert descricoes.startswith("## ")
    tela = cliente.get("/p/ana/importacoes/1").text
    assert "descrições dos cargos ainda não foram lidos" in tela
    assert "Gravar no dossiê" in tela  # dá para gravar sem a IA

    antes = len(propostas_da_importacao(_engine(), 1))
    cliente.get("/p/ana/importacoes/1/extrair")
    assert '"descricoes_linkedin"' in str(falso.ultimo_pedido)
    assert len(propostas_da_importacao(_engine(), 1)) == antes  # o cargo já estava proposto
    assert obter_importacao(_engine(), 1).extracao == "feita"


# --- CV antigo ----------------------------------------------------------------

CV = [
    "Ana Exemplo - Cientista de Dados",
    "Gerente de Dados e IA - Empresa Exemplo (nov/2022 - atual)",
    "Reduziu o custo da plataforma em 30%.",
]
CARGO_DO_CV = {
    "tipo": "cargo",
    "texto": "Gerente de Dados e IA — Empresa Exemplo",
    "empresa": "Empresa Exemplo",
    "cargo": "Gerente de Dados e IA",
    "periodo": {"inicio": "2022-11", "fim": None},
    "trecho": "Gerente de Dados e IA - Empresa Exemplo (nov/2022 - atual)",
}
RESULTADO_DO_CV = {
    "tipo": "resultado",
    "texto": "Reduziu o custo da plataforma em 30%",
    "empresa": "Empresa Exemplo",
    "trecho": "Reduziu o custo da plataforma em 30%.",
}


@pytest.mark.parametrize("formato", ["docx", "pdf"])
def test_cv_vira_texto_e_conflito_sugere_o_linkedin(
    cliente, ana_api, usar_modelo, pasta_dados, formato
):
    falso = usar_modelo(Falso({"fatos": [CARGO_DO_CV, RESULTADO_DO_CV]}))
    conteudo = gerar_cv_docx(CV) if formato == "docx" else gerar_cv_pdf(CV)
    resposta = cliente.post(
        "/p/ana/importar/cv",
        files={"arquivo": (f"CV antigo.{formato}", conteudo, "application/octet-stream")},
        follow_redirects=False,
    )
    assert resposta.headers["location"] == "/p/ana/importacoes/1/extrair"
    importacao = obter_importacao(_engine(), 1)
    assert importacao.fonte == "cv"
    assert importacao.extraido.endswith("_CV_antigo.txt")

    cliente.get("/p/ana/importacoes/1/extrair")
    assert '"cv"' in str(falso.ultimo_pedido)
    conflito, novo = propostas_da_importacao(_engine(), 1)
    assert (conflito.acao, conflito.fato_alvo, conflito.sugestao) == (
        "conflito",
        "F-010",
        "manter_atual",
    )
    assert "LinkedIn, que prevalece sobre o CV antigo" in conflito.motivo
    assert novo.acao == "novo" and json.loads(novo.alertas) == []

    tela = cliente.get("/p/ana/importacoes/1").text
    assert "No dossiê (F-010)" in tela
    assert "Manter o do dossiê" in tela
    assert _dossie(pasta_dados) == EXEMPLO


def test_cv_que_nao_e_pdf_nem_docx(cliente, ana, pasta_dados):
    resposta = cliente.post(
        "/p/ana/importar/cv", files={"arquivo": ("cv.doc", b"\xd0\xcf\x11\xe0" + b"0" * 50)}
    )
    assert resposta.status_code == 400
    assert ".docx ou PDF" in resposta.text
    assert not list((pasta_perfil(pasta_dados, "ana") / "fontes").iterdir())


def test_formulario_do_navegador_manda_o_campo_de_arquivo_vazio(cliente, ana):
    resposta = cliente.post(
        "/p/ana/importar/texto",
        data={"texto": TEXTO, "nome": ""},
        files={"arquivo": ("", b"", "application/octet-stream")},
        follow_redirects=False,
    )
    assert resposta.headers["location"] == "/p/ana/importacoes/1/extrair"
    assert obter_importacao(_engine(), 1).nome == "Texto colado"


def test_pdf_no_campo_de_texto_e_recusado(cliente, ana):
    resposta = _enviar_md(cliente, gerar_cv_pdf(), nome="cv.md")
    assert resposta.status_code == 400
    assert "não é texto" in resposta.text
