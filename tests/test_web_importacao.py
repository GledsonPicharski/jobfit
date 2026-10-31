from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import banco_do_perfil
from app.dossie.formato import escrever_dossie, ler_dossie
from app.dossie.modelos import Periodo
from app.dossie.propostas import obter_importacao, propostas_da_importacao
from app.dossie.versoes import caminho_dossie, versoes
from app.ingestao import arquivos
from app.main import create_app
from app.perfis.servico import criar_perfil, pasta_perfil
from tests.linkedin_pdf_ficticio import gerar_pdf

ORIGEM = "http://127.0.0.1:8765"
RAIZ = Path(__file__).resolve().parents[1]
EXEMPLO = (RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md").read_text(encoding="utf-8")
PDF = gerar_pdf("pt")


@pytest.fixture
def cliente():
    return TestClient(create_app(), base_url=ORIGEM, headers={"Origin": ORIGEM})


@pytest.fixture
def ana(pasta_dados):
    """Perfil com o dossiê de exemplo: importar é atualizar."""
    perfil = criar_perfil(pasta_dados, "Ana Exemplo", "ana")
    caminho_dossie(pasta_dados, "ana").write_text(EXEMPLO, encoding="utf-8")
    return perfil


@pytest.fixture
def bia(pasta_dados):
    """Perfil novo, com o dossiê vazio: importar é montar o dossiê inicial."""
    return criar_perfil(pasta_dados, "Bia Exemplo", "bia")


def _dossie(pasta_dados, slug="ana") -> str:
    return caminho_dossie(pasta_dados, slug).read_text(encoding="utf-8")


def _enviar(cliente, conteudo=PDF, nome="Perfil da Ana.pdf", slug="ana"):
    return cliente.post(
        f"/p/{slug}/importar/arquivo",
        files={"arquivo": (nome, conteudo, "application/octet-stream")},
        follow_redirects=False,
    )


def _propostas(slug="ana", importacao_id=1):
    return propostas_da_importacao(banco_do_perfil(slug), importacao_id)


def _aplicar(cliente, dados=None, slug="ana", importacao_id=1):
    return cliente.post(
        f"/p/{slug}/importacoes/{importacao_id}/aplicar",
        data=dados or {},
        follow_redirects=False,
    )


def _todas_marcadas(slug="ana", importacao_id=1) -> dict:
    return {"aceitas": [str(p.id) for p in _propostas(slug, importacao_id) if p.acao == "novo"]}


# --- atualizar um dossiê que já existe -------------------------------------------


def test_atualizar_dossie_fica_dentro_do_dossie(cliente, ana):
    assert 'href="/p/ana/importar"' not in cliente.get("/p/ana").text.split("</nav>")[0]
    assert 'href="/p/ana/importar"' in cliente.get("/p/ana/dossie").text
    tela = cliente.get("/p/ana/importar").text
    assert "Atualizar dossiê" in tela
    assert 'action="/p/ana/importar/arquivo"' in tela
    assert 'action="/p/ana/importar/texto"' in tela


def test_pdf_do_linkedin_mostra_so_o_que_muda_sem_gravar(cliente, ana, pasta_dados):
    resposta = _enviar(cliente)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/p/ana/importacoes/1"
    assert _dossie(pasta_dados) == EXEMPLO  # nada gravado antes de aplicar

    salvos = sorted((pasta_perfil(pasta_dados, "ana") / "fontes").iterdir())
    pdf = next(s for s in salvos if s.suffix == ".pdf")
    assert pdf.name.endswith("_Perfil_da_Ana.pdf") and pdf.read_bytes() == PDF
    assert any(s.name.endswith("_descricoes.md") for s in salvos)

    tela = cliente.get("/p/ana/importacoes/1").text
    assert "O que muda no dossiê" in tela
    assert "Coordenadora de Ciência de Dados — Empresa Exemplo" in tela
    assert "já estavam no dossiê" in tela
    assert "Gerente de Dados — Empresa Exemplo" not in tela  # F-010, mesmo início
    assert "janeiro de 2018 - fevereiro de 2023" in tela  # trecho de origem
    assert 'type="checkbox" name="aceitas"' in tela
    assert "Aplicar ao dossiê" in tela


def test_aplicar_grava_o_marcado_e_o_desmarcado_nao_volta(cliente, ana, pasta_dados):
    _enviar(cliente)
    novas = [p for p in _propostas() if p.acao == "novo"]
    desmarcada, marcadas = novas[0], novas[1:]

    resposta = _aplicar(cliente, {"aceitas": [str(p.id) for p in marcadas]})
    assert resposta.status_code == 303
    numero = versoes(banco_do_perfil("ana"))[0].versao
    assert resposta.headers["location"] == f"/p/ana/dossie?gravado={numero}"

    doc = ler_dossie(_dossie(pasta_dados))
    novos = [f for f in doc.fatos if f.origem == f"linkedin_pdf {date.today().isoformat()}"]
    assert len(novos) == len(marcadas)
    decisoes = {p.id: p.decisao for p in _propostas()}
    assert decisoes[desmarcada.id] == "rejeitada"
    assert all(decisoes[p.id] == "aprovada" for p in marcadas)

    tela = cliente.get(resposta.headers["location"]).text
    assert f"Dossiê atualizado: versão {numero}" in tela
    assert "Desfazer" in tela

    _enviar(cliente, nome="de novo.pdf")
    textos = {p.chave for p in _propostas(importacao_id=2)}
    assert desmarcada.chave not in textos


def test_corrigir_um_item_antes_de_aplicar(cliente, ana, pasta_dados):
    _enviar(cliente)
    cargo = next(p for p in _propostas() if "Coordenadora" in p.dados)
    dados = _todas_marcadas()
    dados.update(
        {
            f"texto-{cargo.id}": "Coordenadora de Ciência de Dados na Empresa Exemplo",
            f"empresa-{cargo.id}": "Empresa Exemplo",
            f"cargo-{cargo.id}": "Coordenadora de Ciência de Dados",
            f"inicio-{cargo.id}": "2018-01",
            f"fim-{cargo.id}": "2023-02",
        }
    )
    _aplicar(cliente, dados)
    doc = ler_dossie(_dossie(pasta_dados))
    fato = next(f for f in doc.fatos if f.texto.startswith("Coordenadora"))
    assert fato.texto == "Coordenadora de Ciência de Dados na Empresa Exemplo"
    assert fato.periodo == Periodo(inicio="2018-01", fim="2023-02")
    assert {p.id: p.decisao for p in _propostas()}[cargo.id] == "editada"


def test_correcao_invalida_nao_grava_e_mostra_o_erro(cliente, ana, pasta_dados):
    _enviar(cliente)
    proposta = next(p for p in _propostas() if p.acao == "novo")
    dados = {
        "aceitas": [str(proposta.id)],
        f"texto-{proposta.id}": "Texto",
        f"inicio-{proposta.id}": "ontem",
    }
    resposta = _aplicar(cliente, dados)
    assert resposta.status_code == 400
    assert "aviso falha" in resposta.text
    assert _dossie(pasta_dados) == EXEMPLO


def test_email_do_pdf_entra_fora_da_ia(cliente, ana, pasta_dados):
    _enviar(cliente)
    _aplicar(cliente, _todas_marcadas())
    doc = ler_dossie(_dossie(pasta_dados))
    email = next(f for f in doc.fatos if f.texto.startswith("E-mail:"))
    assert email.nao_enviar_ia is True


def test_conflito_mostra_os_dois_periodos_e_a_escolha(cliente, ana, pasta_dados):
    doc = ler_dossie(EXEMPLO)
    f010 = doc.fato("F-010")
    doc.substituir_fato(
        f010.model_copy(update={"periodo": Periodo(inicio="2023-03", fim="2024-01")})
    )
    caminho_dossie(pasta_dados, "ana").write_text(escrever_dossie(doc), encoding="utf-8")

    _enviar(cliente)
    tela = cliente.get("/p/ana/importacoes/1").text
    assert "Diferente do dossiê" in tela
    assert "Manter o do dossiê: <strong>2023-03 – 2024-01</strong>" in tela
    assert "Usar o da fonte: <strong>2023-03 – atual</strong>" in tela

    conflito = next(p for p in _propostas() if p.acao == "conflito")
    _aplicar(cliente, {f"conflito-{conflito.id}": "fonte"})
    assert ler_dossie(_dossie(pasta_dados)).fato("F-010").periodo == Periodo(inicio="2023-03")


def test_desfazer_volta_a_versao_anterior(cliente, ana, pasta_dados):
    cliente.get("/p/ana/dossie")  # registra o dossiê de exemplo como versão
    antes = ler_dossie(_dossie(pasta_dados)).fatos
    _enviar(cliente)
    gravada = _aplicar(cliente, _todas_marcadas()).headers["location"]
    numero = int(gravada.rsplit("=", 1)[1])

    resposta = cliente.post(
        f"/p/ana/dossie/historico/{numero - 1}/restaurar", follow_redirects=False
    )
    assert resposta.status_code == 303
    assert ler_dossie(_dossie(pasta_dados)).fatos == antes
    assert versoes(banco_do_perfil("ana"))[0].motivo == "restauracao"
    assert cliente.post("/p/ana/dossie/historico/99/restaurar").status_code == 404


def test_descartar(cliente, ana, pasta_dados):
    _enviar(cliente)
    resposta = cliente.post("/p/ana/importacoes/1/descartar", follow_redirects=False)
    assert resposta.headers["location"] == "/p/ana/importar"
    assert obter_importacao(banco_do_perfil("ana"), 1).status == "descartada"
    assert _dossie(pasta_dados) == EXEMPLO


# --- dossiê inicial ---------------------------------------------------------------


def test_dossie_vazio_oferece_os_tres_caminhos(cliente, bia):
    tela = cliente.get("/p/bia/dossie").text
    assert "Monte seu dossiê" in tela
    assert "Pelo LinkedIn" in tela and "Pelo que você já tem" in tela and "À mão" in tela
    assert 'action="/p/bia/importar/arquivo"' in tela
    assert "+ Adicionar" in tela


def test_linkedin_num_dossie_vazio_vira_rascunho_aprovado_de_uma_vez(cliente, bia, pasta_dados):
    _enviar(cliente, slug="bia")
    tela = cliente.get("/p/bia/importacoes/1").text
    assert "Rascunho do seu dossiê" in tela
    assert "Usar como meu dossiê" in tela

    resposta = _aplicar(cliente, _todas_marcadas("bia"), slug="bia")
    assert resposta.headers["location"].startswith("/p/bia/dossie?gravado=")
    doc = ler_dossie(_dossie(pasta_dados, "bia"))
    assert len(doc.fatos) == len([p for p in _propostas("bia") if p.acao == "novo"])
    assert "Monte seu dossiê" not in cliente.get("/p/bia/dossie").text


def test_dossie_pronto_num_perfil_vazio_e_adotado_direto(cliente, bia, pasta_dados):
    resposta = _enviar(cliente, EXEMPLO.encode("utf-8"), nome="meu dossiê.md", slug="bia")
    assert resposta.status_code == 303
    assert resposta.headers["location"].startswith("/p/bia/dossie?gravado=")
    doc = ler_dossie(_dossie(pasta_dados, "bia"))
    assert [f.id for f in doc.fatos] == [f.id for f in ler_dossie(EXEMPLO).fatos]
    assert versoes(banco_do_perfil("bia"))[0].motivo == "adocao"
    assert "dossiê enviado" in cliente.get(resposta.headers["location"]).text


def test_dossie_pronto_num_perfil_com_dossie_compara_sem_ia(cliente, ana, pasta_dados):
    doc = ler_dossie(EXEMPLO)
    f010 = doc.fato("F-010")
    doc.substituir_fato(f010.model_copy(update={"texto": "Liderou a área de dados."}))
    outro = escrever_dossie(doc).replace("id: F-010", "id: F-900")
    _enviar(cliente, outro.encode("utf-8"), nome="outro.md")
    assert _dossie(pasta_dados) == EXEMPLO
    importacao = obter_importacao(banco_do_perfil("ana"), 1)
    assert importacao.extracao is None  # sem IA
    assert all(p.acao != "novo" or "F-" not in p.dados for p in _propostas())


def test_dossie_enviado_com_erro_mostra_a_linha(cliente, bia):
    quebrado = "## Formação\n\n```fatos\n- id: F-001\n  tipo: inventado\n  texto: x\n```\n"
    resposta = _enviar(cliente, quebrado.encode("utf-8"), nome="dossie.md", slug="bia")
    assert resposta.status_code == 400
    assert "O dossiê enviado tem um erro" in resposta.text
    assert "Linha 4: fato F-001" in resposta.text


# --- arquivos recusados -------------------------------------------------------------


def test_arquivo_grande_demais_e_recusado(cliente, ana, pasta_dados, monkeypatch):
    monkeypatch.setattr(arquivos, "LIMITE_BYTES", 1000)
    resposta = _enviar(cliente)
    assert resposta.status_code == 413
    assert not list((pasta_perfil(pasta_dados, "ana") / "fontes").iterdir())


def test_binario_desconhecido(cliente, ana, pasta_dados):
    resposta = _enviar(cliente, conteudo=b"\x00\x01\x02 binario", nome="x.bin")
    assert resposta.status_code == 400
    assert "Não reconheci o arquivo" in resposta.text
    assert not list((pasta_perfil(pasta_dados, "ana") / "fontes").iterdir())


def test_importacao_inexistente(cliente, ana):
    assert cliente.get("/p/ana/importacoes/99").status_code == 404
    assert cliente.post("/p/ana/importacoes/99/aplicar").status_code == 404


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
