from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import banco_do_perfil
from app.dossie.formato import escrever_dossie, ler_dossie
from app.dossie.modelos import Periodo
from app.dossie.propostas import propostas_da_importacao
from app.dossie.versoes import caminho_dossie, versoes
from app.ingestao import arquivos
from app.main import create_app
from app.perfis.servico import criar_perfil, pasta_perfil
from tests.linkedin_pdf_ficticio import gerar_pdf

ORIGEM = "http://127.0.0.1:8765"
RAIZ = Path(__file__).resolve().parents[1]
EXEMPLO = (RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md").read_text(encoding="utf-8")
PDF = gerar_pdf("pt")
HTMX = {"HX-Request": "true"}


@pytest.fixture
def cliente():
    return TestClient(create_app(), base_url=ORIGEM, headers={"Origin": ORIGEM})


@pytest.fixture
def ana(pasta_dados):
    perfil = criar_perfil(pasta_dados, "Ana Exemplo", "ana")
    caminho_dossie(pasta_dados, "ana").write_text(EXEMPLO, encoding="utf-8")
    return perfil


def _dossie(pasta_dados) -> str:
    return caminho_dossie(pasta_dados, "ana").read_text(encoding="utf-8")


def _enviar(cliente, conteudo=PDF, nome="Perfil da Ana.pdf"):
    return cliente.post(
        "/p/ana/importar/linkedin",
        files={"arquivo": (nome, conteudo, "application/pdf")},
        follow_redirects=False,
    )


def _propostas():
    return propostas_da_importacao(banco_do_perfil("ana"), 1)


def test_menu_tem_importar_e_tela_explica_o_pdf(cliente, ana):
    assert 'href="/p/ana/importar"' in cliente.get("/p/ana").text
    tela = cliente.get("/p/ana/importar").text
    assert "Salvar como PDF" in tela
    assert 'action="/p/ana/importar/linkedin"' in tela
    assert 'enctype="multipart/form-data"' in tela


def test_enviar_pdf_cria_importacao_sem_tocar_no_dossie(cliente, ana, pasta_dados):
    resposta = _enviar(cliente)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/p/ana/importacoes/1"
    assert _dossie(pasta_dados) == EXEMPLO  # regra 4: nada antes da aprovação

    salvos = list((pasta_perfil(pasta_dados, "ana") / "fontes").iterdir())
    assert len(salvos) == 1
    assert salvos[0].name.endswith("_Perfil_da_Ana.pdf")
    assert salvos[0].read_bytes() == PDF

    tela = cliente.get("/p/ana/importacoes/1").text
    assert "Perfil da Ana.pdf" in tela
    assert "Coordenadora de Ciência de Dados — Empresa Exemplo" in tela
    assert "já estavam no dossiê" in tela
    assert "Gerente de Dados — Empresa Exemplo" not in tela  # F-010, mesmo início
    assert "janeiro de 2018 - fevereiro de 2023" in tela  # trecho de origem


def test_aprovar_e_rejeitar_por_htmx_devolvem_o_cartao(cliente, ana):
    _enviar(cliente)
    primeira, segunda = _propostas()[:2]
    url = f"/p/ana/importacoes/1/propostas/{primeira.id}"

    resposta = cliente.post(url, data={"decisao": "aprovada"}, headers=HTMX)
    assert resposta.status_code == 200
    assert f'id="proposta-{primeira.id}"' in resposta.text
    assert "Aprovada" in resposta.text
    assert 'id="resumo-importacao" hx-swap-oob="true"' in resposta.text

    url = f"/p/ana/importacoes/1/propostas/{segunda.id}"
    cliente.post(url, data={"decisao": "rejeitada"}, headers=HTMX)
    decisoes = {p.id: p.decisao for p in _propostas()}
    assert decisoes[primeira.id] == "aprovada"
    assert decisoes[segunda.id] == "rejeitada"


def test_decidir_sem_htmx_volta_para_a_tela(cliente, ana):
    _enviar(cliente)
    proposta = _propostas()[0]
    resposta = cliente.post(
        f"/p/ana/importacoes/1/propostas/{proposta.id}",
        data={"decisao": "aprovada"},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == f"/p/ana/importacoes/1#proposta-{proposta.id}"


def test_editar_grava_o_texto_da_pessoa(cliente, ana, pasta_dados):
    _enviar(cliente)
    cargo = next(p for p in _propostas() if "Coordenadora" in p.dados)
    cliente.post(
        f"/p/ana/importacoes/1/propostas/{cargo.id}",
        data={
            "decisao": "editada",
            "texto": "Coordenadora de Ciência de Dados na Empresa Exemplo",
            "empresa": "Empresa Exemplo",
            "cargo": "Coordenadora de Ciência de Dados",
            "inicio": "2018-01",
            "fim": "2023-02",
        },
        headers=HTMX,
    )
    cliente.post("/p/ana/importacoes/1/aprovar-pendentes")
    cliente.post("/p/ana/importacoes/1/gravar")
    doc = ler_dossie(_dossie(pasta_dados))
    fato = next(f for f in doc.fatos if f.texto.startswith("Coordenadora"))
    assert fato.texto == "Coordenadora de Ciência de Dados na Empresa Exemplo"
    assert fato.periodo == Periodo(inicio="2018-01", fim="2023-02")


def test_edicao_invalida_mostra_o_erro_no_cartao(cliente, ana):
    _enviar(cliente)
    proposta = _propostas()[0]
    resposta = cliente.post(
        f"/p/ana/importacoes/1/propostas/{proposta.id}",
        data={"decisao": "editada", "texto": "", "inicio": "ontem"},
        headers=HTMX,
    )
    assert resposta.status_code == 200
    assert "aviso falha" in resposta.text
    assert _propostas()[0].decisao == "pendente"


def test_gravar_com_pendente_e_recusado(cliente, ana, pasta_dados):
    _enviar(cliente)
    resposta = cliente.post("/p/ana/importacoes/1/gravar")
    assert resposta.status_code == 409
    assert "pendente(s)" in resposta.text
    assert _dossie(pasta_dados) == EXEMPLO


def test_aprovar_pendentes_e_gravar_leva_ao_diff(cliente, ana, pasta_dados):
    _enviar(cliente)
    rejeitada = _propostas()[0]
    cliente.post(f"/p/ana/importacoes/1/propostas/{rejeitada.id}", data={"decisao": "rejeitada"})
    cliente.post("/p/ana/importacoes/1/aprovar-pendentes")
    resposta = cliente.post("/p/ana/importacoes/1/gravar", follow_redirects=False)
    assert resposta.status_code == 303
    numero = versoes(banco_do_perfil("ana"))[0].versao
    assert resposta.headers["location"] == f"/p/ana/dossie/historico/{numero}"

    doc = ler_dossie(_dossie(pasta_dados))
    novos = [f for f in doc.fatos if f.origem == f"linkedin_pdf {date.today().isoformat()}"]
    assert len(novos) == len(_propostas()) - 1
    assert all(f.texto in _dossie(pasta_dados) for f in novos)

    tela = cliente.get("/p/ana/importacoes/1").text
    assert "Gravada na versão" in tela
    assert "/propostas/" not in tela  # sem botões depois de gravada


def test_email_do_pdf_entra_fora_da_ia(cliente, ana, pasta_dados):
    _enviar(cliente)
    cliente.post("/p/ana/importacoes/1/aprovar-pendentes")
    cliente.post("/p/ana/importacoes/1/gravar")
    doc = ler_dossie(_dossie(pasta_dados))
    email = next(f for f in doc.fatos if f.texto.startswith("E-mail:"))
    assert email.nao_enviar_ia is True


def test_conflito_mostra_os_dois_periodos(cliente, ana, pasta_dados):
    doc = ler_dossie(EXEMPLO)
    f010 = doc.fato("F-010")
    doc.substituir_fato(
        f010.model_copy(update={"periodo": Periodo(inicio="2023-03", fim="2024-01")})
    )
    caminho_dossie(pasta_dados, "ana").write_text(escrever_dossie(doc), encoding="utf-8")

    _enviar(cliente)
    tela = cliente.get("/p/ana/importacoes/1").text
    assert "No dossiê (F-010)" in tela
    assert "2023-03 – 2024-01" in tela
    assert "2023-03 – atual" in tela
    assert "Usar o da fonte" in tela


def test_importar_de_novo_nao_repete_o_rejeitado(cliente, ana):
    _enviar(cliente)
    for proposta in _propostas():
        cliente.post(f"/p/ana/importacoes/1/propostas/{proposta.id}", data={"decisao": "rejeitada"})
    cliente.post("/p/ana/importacoes/1/gravar")
    _enviar(cliente)
    assert propostas_da_importacao(banco_do_perfil("ana"), 2) == []
    assert "Nada novo" in cliente.get("/p/ana/importacoes/2").text


def test_arquivo_grande_demais_e_recusado(cliente, ana, pasta_dados, monkeypatch):
    monkeypatch.setattr(arquivos, "LIMITE_BYTES", 1000)
    resposta = _enviar(cliente)
    assert resposta.status_code == 413
    assert "10 MB" in resposta.text or "grande" in resposta.text
    assert not list((pasta_perfil(pasta_dados, "ana") / "fontes").iterdir())


def test_arquivo_que_nao_e_pdf_do_linkedin(cliente, ana, pasta_dados):
    resposta = _enviar(cliente, conteudo=b"texto qualquer", nome="cv.pdf")
    assert resposta.status_code == 400
    assert "PDF" in resposta.text
    assert not list((pasta_perfil(pasta_dados, "ana") / "fontes").iterdir())


def test_importacao_inexistente_ou_proposta_de_outra_importacao(cliente, ana):
    assert cliente.get("/p/ana/importacoes/99").status_code == 404
    _enviar(cliente)
    proposta = _propostas()[0]
    resposta = cliente.post(
        f"/p/ana/importacoes/99/propostas/{proposta.id}", data={"decisao": "aprovada"}
    )
    assert resposta.status_code == 404


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("Perfil da Ana.pdf", "Perfil_da_Ana.pdf"),
        ("..\\..\\segredo.pdf", "segredo.pdf"),
        ("currículo — versão 2.pdf", "currículo_versão_2.pdf"),
        ("", "arquivo"),
    ],
)
def test_nome_seguro(nome, esperado):
    assert arquivos.nome_seguro(nome) == esperado
