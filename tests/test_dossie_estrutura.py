from pathlib import Path

import pytest

from app.dossie.estrutura import esqueleto, inserir_fatos, proximo_id
from app.dossie.formato import escrever_dossie, ler_dossie
from app.dossie.modelos import Fato, Periodo

RAIZ = Path(__file__).resolve().parents[1]
EXEMPLO = (RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md").read_text(encoding="utf-8")


def _fato(id_: str, tipo: str, texto: str, **campos) -> Fato:
    return Fato(id=id_, tipo=tipo, texto=texto, **campos)


def _secao(texto: str, titulo: str) -> str:
    """O trecho do texto entre o título e o próximo título de mesmo nível ou acima."""
    nivel = titulo.split(" ")[0]
    inicio = texto.index(titulo)
    resto = texto[inicio + len(titulo) :]
    fins = [resto.find("\n" + "#" * n + " ") for n in range(1, len(nivel) + 1)]
    fins = [f for f in fins if f >= 0]
    return resto[: min(fins)] if fins else resto


def test_esqueleto_tem_as_secoes_e_nenhum_fato():
    texto = esqueleto("ana-exemplo", "Ana Exemplo")
    doc = ler_dossie(texto)
    assert doc.metadados["perfil"] == "ana-exemplo"
    assert doc.fatos == []
    assert "# Dossiê de carreira — Ana Exemplo" in texto
    for titulo in (
        "Objetivo",
        "Experiências",
        "Formação",
        "Competências",
        "Idiomas",
        "Certificações",
    ):
        assert titulo in texto


def test_proximo_id():
    assert proximo_id(ler_dossie(EXEMPLO)) == "F-051"
    assert proximo_id(ler_dossie("# vazio\n")) == "F-001"


def test_proximo_id_ignora_buracos_e_mantem_tres_digitos():
    doc = ler_dossie(
        "```fatos\n- id: F-7\n  tipo: cargo\n  texto: x\n```\n".replace("F-7", "F-007")
    )
    assert proximo_id(doc) == "F-008"


def test_resultado_de_empresa_existente_entra_no_bloco_dela():
    doc = ler_dossie(EXEMPLO)
    novo = _fato("F-051", "resultado", "Montou o time de dados.", empresa="Empresa Exemplo")
    inserir_fatos(doc, [novo])
    texto = escrever_dossie(doc)

    secao = _secao(texto, "### Empresa Exemplo")
    assert "Montou o time de dados." in secao
    assert ler_dossie(texto).fato("F-051") == novo
    # Os outros blocos não mudam.
    assert _secao(texto, "## 4. Formação") == _secao(EXEMPLO, "## 4. Formação")


def test_empresa_nova_ganha_subtitulo_dentro_de_experiencias():
    doc = ler_dossie(EXEMPLO)
    cargo = _fato(
        "F-051",
        "cargo",
        "Estagiária na Startup Inventada.",
        empresa="Startup Inventada",
        cargo="Estagiária",
        periodo=Periodo(inicio="2016-01", fim="2017-12"),
    )
    inserir_fatos(doc, [cargo])
    texto = escrever_dossie(doc)

    experiencias = _secao(texto, "## 3. Experiências")
    assert "### Startup Inventada" in experiencias
    assert "Estagiária na Startup Inventada." in _secao(texto, "### Startup Inventada")
    assert texto.index("### Startup Inventada") < texto.index("## 4. Formação")


def test_subtitulo_com_cargo_e_datas_ainda_casa_com_a_empresa():
    texto = (
        "## 3. Experiências\n\n### Empresa Exemplo — Gerente (2023 – atual)\n\nNarrativa.\n\n"
        "## 4. Formação\n"
    )
    doc = ler_dossie(texto)
    inserir_fatos(doc, [_fato("F-001", "resultado", "Fez algo.", empresa="empresa exemplo")])
    saida = escrever_dossie(doc)
    assert saida.count("###") == 1
    assert "Fez algo." in _secao(saida, "### Empresa Exemplo")


@pytest.mark.parametrize(
    ("tipo", "secao"),
    [
        ("formacao", "## 4. Formação"),
        ("competencia", "## 5. Competências e ferramentas"),
        ("ferramenta", "## 5. Competências e ferramentas"),
        ("idioma", "## 6. Idiomas"),
        ("certificacao", "## 7. Certificações"),
        ("preferencia", "## 1. Objetivo e preferências"),
        ("restricao", "## 1. Objetivo e preferências"),
    ],
)
def test_fato_sem_empresa_vai_para_a_secao_do_tipo(tipo, secao):
    doc = ler_dossie(EXEMPLO)
    inserir_fatos(doc, [_fato("F-051", tipo, "Fato novo do teste.")])
    texto = escrever_dossie(doc)
    assert "Fato novo do teste." in _secao(texto, secao)
    assert ler_dossie(texto).fato("F-051").tipo == tipo


def test_secao_sem_bloco_ganha_um_bloco_novo():
    doc = ler_dossie(EXEMPLO)
    inserir_fatos(doc, [_fato("F-051", "certificacao", "Certificação Fictícia em Nuvem.")])
    texto = escrever_dossie(doc)
    secao = _secao(texto, "## 7. Certificações")
    assert secao.startswith("\n\nNenhuma ainda.\n\n```fatos\n- id: F-051\n")
    assert texto.endswith("```\n")


def test_secao_que_falta_e_criada_no_fim():
    doc = ler_dossie("# Dossiê\n\n## Resumo\n\nTexto.\n")
    inserir_fatos(doc, [_fato("F-001", "idioma", "Espanhol básico.")])
    texto = escrever_dossie(doc)
    assert texto.startswith("# Dossiê\n\n## Resumo\n\nTexto.\n\n## Idiomas\n\n```fatos\n")
    assert ler_dossie(texto).fato("F-001").texto == "Espanhol básico."


def test_cargo_sem_experiencias_cria_secao_e_subtitulo():
    doc = ler_dossie("# Dossiê\n")
    inserir_fatos(doc, [_fato("F-001", "cargo", "Analista.", empresa="Empresa Exemplo")])
    texto = escrever_dossie(doc)
    assert "## Experiências\n\n### Empresa Exemplo\n\n```fatos\n" in texto


def test_titulo_dentro_de_bloco_de_codigo_nao_conta():
    texto = "# Dossiê\n\n```md\n## Idiomas\n```\n"
    doc = ler_dossie(texto)
    inserir_fatos(doc, [_fato("F-001", "idioma", "Francês básico.")])
    saida = escrever_dossie(doc)
    assert saida.startswith(texto)
    assert saida.count("## Idiomas") == 2


def test_varios_fatos_na_ordem_e_ida_e_volta():
    doc = ler_dossie(esqueleto("ana", "Ana"))
    fatos = [
        _fato("F-001", "cargo", "Gerente.", empresa="Empresa Exemplo", cargo="Gerente"),
        _fato("F-002", "resultado", "Resultado A.", empresa="Empresa Exemplo"),
        _fato("F-003", "idioma", "Inglês C1."),
        _fato("F-004", "resultado", "Resultado B.", empresa="Empresa Exemplo"),
    ]
    inserir_fatos(doc, fatos)
    texto = escrever_dossie(doc)
    relido = ler_dossie(texto)
    assert [f.id for f in relido.fatos] == ["F-001", "F-002", "F-004", "F-003"]
    assert texto.count("### Empresa Exemplo") == 1
    assert escrever_dossie(relido) == texto
