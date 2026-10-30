from datetime import date
from pathlib import Path

import pytest

from app.dossie.formato import ErroDossie, escrever_dossie, ler_dossie
from app.dossie.modelos import Fato, Periodo

RAIZ = Path(__file__).resolve().parents[1]
EXEMPLO = RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md"


@pytest.fixture
def texto_exemplo() -> str:
    return EXEMPLO.read_text(encoding="utf-8")


# --- ida e volta --------------------------------------------------------------


def test_ida_e_volta_sem_perda(texto_exemplo):
    assert escrever_dossie(ler_dossie(texto_exemplo)) == texto_exemplo


def test_le_frontmatter_e_fatos(texto_exemplo):
    doc = ler_dossie(texto_exemplo)
    assert doc.metadados["perfil"] == "ana-exemplo"
    assert doc.metadados["versao"] == 3
    assert [f.id for f in doc.fatos][:3] == ["F-001", "F-002", "F-010"]
    cargo = doc.fato("F-010")
    assert cargo.tipo == "cargo"
    assert cargo.empresa == "Empresa Exemplo"
    assert cargo.periodo == Periodo(inicio="2023-03", fim=None)
    assert doc.fato("F-030").periodo == Periodo(inicio="2010", fim="2014")
    assert doc.fato("F-014").metricas == {"leituras_automatizadas": ">80%"}


def test_privado_e_nao_enviar_ia(texto_exemplo):
    doc = ler_dossie(texto_exemplo)
    assert doc.fato("F-002").privado is True
    assert doc.fato("F-002").nao_enviar_ia is True
    assert doc.fato("F-001").nao_enviar_ia is False


def test_campo_extra_escrito_a_mao_e_preservado(texto_exemplo):
    doc = ler_dossie(texto_exemplo)
    fato = doc.fato("F-014")
    assert fato.model_extra == {"observacao_ana": "confirmar o número com a equipe de operações"}

    # Mesmo reserializado (bloco alterado), o campo extra continua lá.
    doc.substituir_fato(fato.model_copy(update={"privado": True}))
    relido = ler_dossie(escrever_dossie(doc)).fato("F-014")
    assert relido.privado is True
    assert relido.model_extra == fato.model_extra


def test_bom_e_crlf_do_bloco_de_notas_sao_normalizados(texto_exemplo):
    windows = "﻿" + texto_exemplo.replace("\n", "\r\n")
    assert escrever_dossie(ler_dossie(windows)) == texto_exemplo


def test_acentos_travessao_e_emoji_sobrevivem(texto_exemplo):
    saida = escrever_dossie(ler_dossie(texto_exemplo))
    for trecho in ("Dossiê", "—", "🔒", "Consultoria Fictícia", "ç"):
        assert trecho in saida


def test_dossie_sem_frontmatter_e_sem_fatos():
    texto = "# Só narrativa\n\nNada estruturado ainda.\n"
    doc = ler_dossie(texto)
    assert doc.metadados == {}
    assert doc.fatos == []
    assert escrever_dossie(doc) == texto


def test_bloco_de_codigo_comum_nao_e_lido_como_fatos():
    texto = "# Notas\n\n```yaml\n- id: F-999\n  tipo: cargo\n```\n\n```\n```fatos\n```\n"
    doc = ler_dossie(texto)
    assert doc.fatos == []
    assert escrever_dossie(doc) == texto


def test_bloco_de_fatos_vazio():
    texto = "# Dossiê\n\n```fatos\n```\n"
    doc = ler_dossie(texto)
    assert doc.fatos == []
    assert escrever_dossie(doc) == texto


# --- alterações -----------------------------------------------------------------


def test_alterar_um_fato_so_reescreve_o_bloco_dele(texto_exemplo):
    doc = ler_dossie(texto_exemplo)
    doc.substituir_fato(doc.fato("F-021").model_copy(update={"privado": True}))
    saida = escrever_dossie(doc)

    # O comentário de outro bloco continua, byte a byte.
    assert "privado: true   # 🔒 nunca vai para CV" in saida
    relido = ler_dossie(saida)
    assert relido.fato("F-021").privado is True
    assert relido.fato("F-020") == doc.fato("F-020")
    assert relido.fatos == doc.fatos
    # O que está fora do bloco alterado não muda.
    inicio = texto_exemplo.index("### Consultoria Fictícia")
    assert saida[:inicio] == texto_exemplo[:inicio]


def test_bloco_reescrito_e_legivel(texto_exemplo):
    doc = ler_dossie(texto_exemplo)
    doc.substituir_fato(doc.fato("F-021").model_copy(update={"privado": True}))
    saida = escrever_dossie(doc)
    assert "  texto: Reduziu de 5 para 2 dias o fechamento dos relatórios de operação.\n" in saida
    assert "  metricas: {dias_antes: 5, dias_depois: 2}\n" in saida
    assert "  periodo: {inicio: 2018-01, fim: 2023-02}\n" in saida


def test_substituir_fato_inexistente_da_erro(texto_exemplo):
    doc = ler_dossie(texto_exemplo)
    with pytest.raises(KeyError):
        doc.substituir_fato(Fato(id="F-999", tipo="cargo", texto="x"))


def test_alterar_metadado_preserva_o_resto_do_frontmatter(texto_exemplo):
    doc = ler_dossie(texto_exemplo)
    doc.definir_metadado("versao", 4)
    doc.definir_metadado("atualizado", date(2026, 10, 30))
    doc.definir_metadado("novo_campo", "sim")
    saida = escrever_dossie(doc)

    assert saida.startswith("---\nperfil: ana-exemplo\nversao: 4\natualizado: 2026-10-30\n")
    assert "idiomas_cv: [pt, en]\nnovo_campo: sim\n---\n" in saida
    assert ler_dossie(saida).metadados["versao"] == 4


def test_definir_metadado_sem_frontmatter_cria_um():
    doc = ler_dossie("# Dossiê\n")
    doc.definir_metadado("versao", 1)
    assert escrever_dossie(doc) == "---\nversao: 1\n---\n# Dossiê\n"


# --- normalização do modelo ---------------------------------------------------


@pytest.mark.parametrize(
    ("escrito", "lido"), [("Competência", "competencia"), ("FORMAÇÃO", "formacao")]
)
def test_tipo_aceita_acento_e_maiuscula(escrito, lido):
    assert Fato(id="F-001", tipo=escrito, texto="x").tipo == lido


def test_periodo_aceita_data_completa_e_atual():
    texto = (
        "```fatos\n- id: F-001\n  tipo: cargo\n  texto: x\n"
        "  periodo: {inicio: 2023-03-15, fim: atual}\n```\n"
    )
    assert ler_dossie(texto).fato("F-001").periodo == Periodo(inicio="2023-03-15", fim=None)


# --- erros com a linha certa -------------------------------------------------


def _com_bloco(conteudo: str) -> str:
    # O conteúdo do bloco começa na linha 5.
    return f"# Dossiê\n\nTexto.\n```fatos\n{conteudo}```\n"


def test_yaml_quebrado_aponta_a_linha():
    texto = _com_bloco("- id: F-001\n  tipo: cargo\n  texto: [sem fechar\n")
    with pytest.raises(ErroDossie) as erro:
        ler_dossie(texto)
    assert 5 <= erro.value.linha <= 8
    assert "YAML" in str(erro.value)


def test_campo_invalido_aponta_a_linha_do_fato():
    texto = _com_bloco(
        "- id: F-001\n  tipo: cargo\n  texto: ok\n- id: F-002\n  tipo: inventado\n  texto: x\n"
    )
    with pytest.raises(ErroDossie) as erro:
        ler_dossie(texto)
    assert erro.value.linha == 8
    assert "F-002" in str(erro.value)
    assert "tipo" in str(erro.value)


def test_id_duplicado_aponta_a_segunda_ocorrencia():
    texto = _com_bloco(
        "- id: F-001\n  tipo: cargo\n  texto: a\n- id: F-001\n  tipo: cargo\n  texto: b\n"
    )
    with pytest.raises(ErroDossie) as erro:
        ler_dossie(texto)
    assert erro.value.linha == 8
    assert "duplicado" in str(erro.value)


def test_bloco_sem_fechar_aponta_a_abertura():
    with pytest.raises(ErroDossie) as erro:
        ler_dossie("# Dossiê\n\n```fatos\n- id: F-001\n")
    assert erro.value.linha == 3
    assert "fechar" in str(erro.value)


def test_bloco_que_nao_e_lista():
    with pytest.raises(ErroDossie) as erro:
        ler_dossie(_com_bloco("id: F-001\n"))
    assert erro.value.linha == 5
    assert "lista" in str(erro.value)


def test_frontmatter_quebrado():
    with pytest.raises(ErroDossie) as erro:
        ler_dossie("---\nversao: [1\n---\n# Dossiê\n")
    assert erro.value.linha >= 2


def test_frontmatter_sem_fechar():
    with pytest.raises(ErroDossie) as erro:
        ler_dossie("---\nversao: 1\n# Dossiê\n")
    assert erro.value.linha == 1
