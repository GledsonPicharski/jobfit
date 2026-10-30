import json
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.db import banco_do_perfil
from app.dossie.estrutura import inserir_fatos, proximo_id
from app.dossie.formato import ErroDossie, ler_dossie
from app.dossie.modelos import Fato
from app.dossie.tabelas import VersaoDossie
from app.dossie.versoes import (
    alterar_dossie,
    caminho_dossie,
    carregar_dossie,
    diferenca,
    diff_texto,
    registrar_edicao_manual,
    versoes,
)
from app.perfis.servico import criar_perfil

RAIZ = Path(__file__).resolve().parents[1]
EXEMPLO = (RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md").read_text(encoding="utf-8")


@pytest.fixture
def ana(pasta_dados):
    return criar_perfil(pasta_dados, "Ana Exemplo", "ana")


@pytest.fixture
def engine(ana):
    return banco_do_perfil("ana")


def _arquivo(pasta_dados) -> Path:
    return caminho_dossie(pasta_dados, "ana")


def _novo_fato(doc, texto="Idioma novo.") -> None:
    inserir_fatos(doc, [Fato(id=proximo_id(doc), tipo="idioma", texto=texto)])


def test_carregar_cria_o_dossie_na_primeira_vez(pasta_dados, ana, engine):
    doc = carregar_dossie(pasta_dados, engine, ana)

    arquivo = _arquivo(pasta_dados)
    assert arquivo.is_file()
    assert doc.metadados["versao"] == 1
    assert "Ana Exemplo" in arquivo.read_text(encoding="utf-8")
    assert (arquivo.parent / "historico" / "dossie_v1.md").is_file()
    [v1] = versoes(engine)
    assert (v1.versao, v1.motivo) == (1, "criacao")


def test_alterar_sobe_a_versao_e_guarda_historico(pasta_dados, ana, engine):
    carregar_dossie(pasta_dados, engine, ana)
    versao = alterar_dossie(pasta_dados, engine, ana, "edicao_app", _novo_fato)

    assert versao.versao == 2
    texto = _arquivo(pasta_dados).read_text(encoding="utf-8")
    doc = ler_dossie(texto)
    assert doc.metadados["versao"] == 2
    assert doc.fato("F-001").texto == "Idioma novo."
    historico = _arquivo(pasta_dados).parent / "historico"
    assert (historico / "dossie_v2.md").read_text(encoding="utf-8") == texto
    assert "F-001" not in (historico / "dossie_v1.md").read_text(encoding="utf-8")
    assert json.loads(versao.resumo) == {"adicionados": ["F-001"], "alterados": [], "removidos": []}


def test_edicao_manual_vira_versao_antes_da_alteracao_do_app(pasta_dados, ana, engine):
    carregar_dossie(pasta_dados, engine, ana)
    arquivo = _arquivo(pasta_dados)
    arquivo.write_text(
        arquivo.read_text(encoding="utf-8") + "\nNota escrita à mão — com acento.\n",
        encoding="utf-8",
    )

    versao = alterar_dossie(pasta_dados, engine, ana, "edicao_app", _novo_fato)

    assert [(v.versao, v.motivo) for v in versoes(engine)] == [
        (3, "edicao_app"),
        (2, "edicao_manual"),
        (1, "criacao"),
    ]
    assert versao.versao == 3
    texto = arquivo.read_text(encoding="utf-8")
    assert "Nota escrita à mão — com acento." in texto  # nada se perde
    assert "Idioma novo." in texto


def test_registrar_edicao_manual_sem_mudanca_nao_cria_versao(pasta_dados, ana, engine):
    carregar_dossie(pasta_dados, engine, ana)
    assert registrar_edicao_manual(pasta_dados, engine, ana) is None
    assert len(versoes(engine)) == 1


def test_crlf_do_bloco_de_notas_nao_conta_como_edicao(pasta_dados, ana, engine):
    carregar_dossie(pasta_dados, engine, ana)
    arquivo = _arquivo(pasta_dados)
    texto = arquivo.read_text(encoding="utf-8")
    arquivo.write_bytes(("﻿" + texto.replace("\n", "\r\n")).encode("utf-8"))
    assert registrar_edicao_manual(pasta_dados, engine, ana) is None


def test_dossie_existente_sem_historico_mantem_a_versao_do_arquivo(pasta_dados, ana, engine):
    arquivo = _arquivo(pasta_dados)
    arquivo.write_text(EXEMPLO, encoding="utf-8")

    doc = carregar_dossie(pasta_dados, engine, ana)
    assert doc.metadados["versao"] == 3
    [v3] = versoes(engine)
    assert (v3.versao, v3.motivo) == (3, "edicao_manual")

    versao = alterar_dossie(pasta_dados, engine, ana, "edicao_app", _novo_fato)
    assert versao.versao == 4
    assert ler_dossie(arquivo.read_text(encoding="utf-8")).fato("F-051").texto == "Idioma novo."


def test_dossie_quebrado_nao_e_gravado(pasta_dados, ana, engine):
    carregar_dossie(pasta_dados, engine, ana)
    arquivo = _arquivo(pasta_dados)
    quebrado = arquivo.read_text(encoding="utf-8") + "\n```fatos\n- id: [quebrado\n```\n"
    arquivo.write_text(quebrado, encoding="utf-8")

    with pytest.raises(ErroDossie):
        alterar_dossie(pasta_dados, engine, ana, "edicao_app", _novo_fato)
    with pytest.raises(ErroDossie):
        carregar_dossie(pasta_dados, engine, ana)

    assert arquivo.read_text(encoding="utf-8") == quebrado
    assert len(versoes(engine)) == 1


def test_alteracao_que_falha_nao_grava_nada(pasta_dados, ana, engine):
    carregar_dossie(pasta_dados, engine, ana)
    antes = _arquivo(pasta_dados).read_text(encoding="utf-8")

    def falhar(doc):
        _novo_fato(doc)
        raise RuntimeError("no meio")

    with pytest.raises(RuntimeError):
        alterar_dossie(pasta_dados, engine, ana, "edicao_app", falhar)
    assert _arquivo(pasta_dados).read_text(encoding="utf-8") == antes
    assert len(versoes(engine)) == 1


def test_versao_registra_importacao_de_origem(pasta_dados, ana, engine):
    carregar_dossie(pasta_dados, engine, ana)
    alterar_dossie(pasta_dados, engine, ana, "importacao", _novo_fato, importacao_id=7)
    with Session(engine) as sessao:
        ultima = sessao.exec(select(VersaoDossie).order_by(VersaoDossie.versao.desc())).first()
    assert ultima.importacao_id == 7


# --- diferença ------------------------------------------------------------------


def test_diferenca_por_id():
    antes = ler_dossie(EXEMPLO).fatos
    depois = [f for f in antes if f.id != "F-041"]
    depois = [f.model_copy(update={"privado": True}) if f.id == "F-021" else f for f in depois]
    depois.append(Fato(id="F-051", tipo="idioma", texto="Espanhol."))

    dif = diferenca(antes, depois)
    assert dif.adicionados == ["F-051"]
    assert dif.alterados == ["F-021"]
    assert dif.removidos == ["F-041"]
    assert not diferenca(antes, antes)


def test_diff_texto_mostra_linhas_alteradas():
    linhas = diff_texto("a\nb\n", "a\nc\n")
    assert "-b" in linhas
    assert "+c" in linhas
