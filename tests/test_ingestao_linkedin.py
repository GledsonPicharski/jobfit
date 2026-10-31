import pytest

from app.dossie.modelos import Periodo
from app.ingestao.linkedin_pdf import (
    ErroLeitura,
    Linha,
    interpretar,
    ler_linkedin_pdf,
    ler_periodo,
)
from tests.linkedin_pdf_ficticio import gerar_pdf


@pytest.fixture(scope="module")
def pt():
    return ler_linkedin_pdf(gerar_pdf("pt"))


@pytest.fixture(scope="module")
def en():
    return ler_linkedin_pdf(gerar_pdf("en"))


def _por_tipo(perfil, tipo):
    return [c for c in perfil.candidatos if c.tipo == tipo]


# --- datas ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("agosto de 2024 - Present (2 anos 3 meses)", Periodo(inicio="2024-08")),
        ("março de 2021 - agosto de 2021 (6 meses)", Periodo(inicio="2021-03", fim="2021-08")),
        ("agosto de 2024 - o momento (2 anos)", Periodo(inicio="2024-08")),
        ("August 2024 - Present (2 years 3 months)", Periodo(inicio="2024-08")),
        ("Dec 2012 - Jun 2018 (5 years 7 months)", Periodo(inicio="2012-12", fim="2018-06")),
        ("2007 - 2011", Periodo(inicio="2007", fim="2011")),
        ("fevereiro de 2022 - janeiro de 2024", Periodo(inicio="2022-02", fim="2024-01")),
        ("2019", Periodo(inicio="2019", fim="2019")),
    ],
)
def test_le_periodos_em_portugues_e_ingles(texto, esperado):
    assert ler_periodo(texto) == esperado


@pytest.mark.parametrize(
    "texto", ["4 anos 5 meses", "Curitiba, Paraná, Brasil", "Liderei 4 times."]
)
def test_o_que_nao_e_periodo(texto):
    assert ler_periodo(texto) is None


# --- coluna principal -------------------------------------------------------------


@pytest.mark.parametrize("perfil", ["pt", "en"])
def test_nome_titulo_e_local(perfil, request):
    lido = request.getfixturevalue(perfil)
    assert lido.nome == "Ana Exemplo"
    assert lido.titulo == "Gerente de Dados | Machine Learning | Crédito"
    assert lido.local == "Curitiba, Paraná, Brasil"


@pytest.mark.parametrize("perfil", ["pt", "en"])
def test_cargos_com_empresa_e_periodo(perfil, request):
    cargos = _por_tipo(request.getfixturevalue(perfil), "cargo")
    assert [(c.empresa, c.cargo, c.periodo) for c in cargos] == [
        ("Empresa Exemplo", "Gerente de Dados", Periodo(inicio="2023-03")),
        (
            "Empresa Exemplo",
            "Coordenadora de Ciência de Dados",
            Periodo(inicio="2018-01", fim="2023-02"),
        ),
        (
            "Consultoria Fictícia",
            "Analista de Dados Pleno",
            Periodo(inicio="2014-04", fim="2017-12"),
        ),
    ]
    assert cargos[0].texto == "Gerente de Dados — Empresa Exemplo"
    assert all(c.fonte == "linkedin_pdf" and c.trecho for c in cargos)


def test_trecho_do_cargo_e_o_texto_do_pdf(pt):
    cargo = _por_tipo(pt, "cargo")[1]
    assert cargo.trecho == (
        "Empresa Exemplo\nCoordenadora de Ciência de Dados\n"
        "janeiro de 2018 - fevereiro de 2023 (5 anos 2 meses)"
    )


def test_descricoes_ficam_para_a_ia_com_o_cargo(pt):
    primeira, segunda, terceira = pt.descricoes[1:]
    assert pt.descricoes[0].cargo is None  # o resumo
    assert "Lidero times de dados há 8 anos" in pt.descricoes[0].texto
    assert primeira.empresa == "Empresa Exemplo"
    assert primeira.cargo == "Gerente de Dados"
    assert primeira.texto == (
        "Lidero o time de dados de crédito, com 6 pessoas.\n"
        "- Lançou o Leitor Automático: mais de 80% das leituras automatizadas."
    )
    assert segunda.texto == "Reduziu de 5 para 2 dias o fechamento dos relatórios."
    assert "Curitiba" not in segunda.texto  # o local, em cinza, não é descrição
    assert terceira.empresa == "Consultoria Fictícia"


@pytest.mark.parametrize("perfil", ["pt", "en"])
def test_formacao_com_periodo_quebrado_em_duas_linhas(perfil, request):
    formacao = _por_tipo(request.getfixturevalue(perfil), "formacao")
    assert [(c.empresa, c.periodo) for c in formacao] == [
        ("Universidade Fictícia do Paraná", Periodo(inicio="2010", fim="2014")),
        ("Escola Exemplo de Negócios", Periodo(inicio="2019-02", fim="2021-01")),
        ("Colégio Técnico Exemplo", None),
    ]
    assert formacao[2].texto == "Técnico em Eletrônica — Colégio Técnico Exemplo"


def test_formacao_em_portugues(pt):
    formacao = _por_tipo(pt, "formacao")
    assert formacao[0].texto == "Bacharelado, Estatística — Universidade Fictícia do Paraná"
    assert formacao[1].texto == (
        "Pós-graduação Lato Sensu, Gestão de Projetos — Escola Exemplo de Negócios"
    )


# --- barra lateral ----------------------------------------------------------------


@pytest.mark.parametrize("perfil", ["pt", "en"])
def test_barra_lateral(perfil, request):
    lido = request.getfixturevalue(perfil)
    assert [c.texto for c in _por_tipo(lido, "competencia")] == [
        "Machine Learning",
        "Análise de Sobrevivência",
    ]
    assert [c.texto for c in _por_tipo(lido, "idioma")] == [
        "Português: nativo ou bilíngue",
        "Inglês: profissional",
    ]
    assert [c.texto for c in _por_tipo(lido, "certificacao")] == [
        "Introdução Fictícia a Dados",
        "Engenharia de Software para Cientistas Fictícios",
    ]
    assert [c.texto for c in _por_tipo(lido, "premio")] == ["1st place - Hackathon Exemplo 2019"]


def test_contato_sem_rotulos_e_com_email_fora_da_ia(pt):
    contatos = {c.texto: c for c in _por_tipo(pt, "contato")}
    email = "E-mail: ana.exemplo" + "@exemplo.test"
    assert set(contatos) == {
        email,
        "LinkedIn: linkedin.com/in/ana-exemplo",
        "github.com/anaexemplo",
        "Curitiba, Paraná, Brasil",
    }
    assert contatos[email].nao_enviar_ia is True
    assert contatos["github.com/anaexemplo"].nao_enviar_ia is False


def _lat(top, texto, tamanho=10.5):
    return Linha(1, top, 21, tamanho, False, texto)


def _principal(pagina, top, texto, tamanho=10.5, cinza=False):
    return Linha(pagina, top, 223, tamanho, cinza, texto)


def _cabeca():
    return [_principal(1, 48, "Fulana", 26), _principal(1, 140, "Experiência", 15.8)]


def test_contatos_colados_separados_pelo_rotulo():
    linhas = [
        _lat(46, "Contato", 13),
        _lat(91, "www.linkedin.com/in/fulana-", 11),
        _lat(105, "tal (LinkedIn)", 11),
        _lat(119, "github.com/fulana/", 11),
        _lat(132, "(Portfolio)", 11),
        _lat(145, "lattes.cnpq.br/123", 11),
        _lat(158, "(Other)", 11),
        *_cabeca(),
    ]
    contatos = [c.texto for c in interpretar(linhas).candidatos if c.tipo == "contato"]
    assert contatos == [
        "LinkedIn: linkedin.com/in/fulana-tal",
        "github.com/fulana",
        "lattes.cnpq.br/123",
    ]


def test_entidade_html_do_pdf_e_decodificada():
    linhas = [
        *_cabeca(),
        _principal(1, 170, "Empresa Fictícia", 12),
        _principal(1, 190, "Gerente de Data &amp; IA", 11.5),
        _principal(1, 205, "2020 - 2021"),
        _principal(1, 225, "Liderou o time de Data &amp; IA."),
    ]
    lido = interpretar(linhas)
    assert lido.candidatos[0].cargo == "Gerente de Data & IA"
    assert lido.descricoes[0].texto == "Liderou o time de Data & IA."


@pytest.mark.parametrize(
    ("fim_da_pagina", "inicio_da_seguinte", "continua"),
    [
        ("- Fez uma coisa, que continua", "na página seguinte.", True),
        ("- Fez uma coisa.", "Stack: R, SQL.", False),
    ],
)
def test_paragrafo_na_virada_de_pagina(fim_da_pagina, inicio_da_seguinte, continua):
    linhas = [
        *_cabeca(),
        _principal(1, 170, "Empresa Fictícia", 12),
        _principal(1, 190, "Analista", 11.5),
        _principal(1, 205, "2020 - 2021"),
        _principal(1, 743, fim_da_pagina),
        _principal(2, 48, inicio_da_seguinte),
    ]
    paragrafos = interpretar(linhas).descricoes[0].texto.split("\n")
    if continua:
        assert paragrafos == [f"{fim_da_pagina} {inicio_da_seguinte}"]
    else:
        assert paragrafos == [fim_da_pagina, inicio_da_seguinte]


def test_idioma_original_fica_no_trecho(pt):
    ingles = _por_tipo(pt, "idioma")[1]
    assert ingles.trecho == "English (Professional Working)"


# --- erros ------------------------------------------------------------------------


def test_pdf_que_nao_e_do_linkedin():
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.text(20, 20, "Um documento qualquer.")
    with pytest.raises(ErroLeitura, match="não parece"):
        ler_linkedin_pdf(bytes(pdf.output()))


def test_arquivo_que_nao_e_pdf():
    with pytest.raises(ErroLeitura, match="PDF"):
        ler_linkedin_pdf(b"isto nao e um pdf")


def test_interpretar_linhas_soltas_sem_experiencia():
    linhas = [Linha(1, 50, 223, 26, False, "Fulano")]
    with pytest.raises(ErroLeitura):
        interpretar(linhas)
