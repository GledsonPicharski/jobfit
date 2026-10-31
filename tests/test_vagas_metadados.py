from decimal import Decimal

import pytest

from app.dossie.modelos import Fato
from app.vagas.metadados import (
    Salario,
    extrair_metadados,
    idioma_do_texto,
    ingles_exigido,
    ler_salario,
    modalidade,
    nivel_ingles_declarado,
    senioridade,
)

RS = "R" + "$"  # montado aqui: "R$ e número" escrito literal, o pre-commit barra o teste


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Modelo de trabalho: Remoto\nAtuação com times — ação contínua.", "remoto"),
        ("Vaga 100% home office para todo o Brasil.", "remoto"),
        ("Fully remote position, work from anywhere.", "remoto"),
        ("Modelo híbrido: 2 dias no escritório em Curitiba.", "hibrido"),
        ("Hybrid role in São Paulo.", "hibrido"),
        ("Atuação presencial na sede, em Joinville.", "presencial"),
        ("This is an on-site role.", "presencial"),
        ("Modalidade: Presencial\nBenefícios: auxílio home office", "presencial"),
        ("Sem nada sobre o local.", None),
    ],
)
def test_modalidade(texto, esperado):
    assert modalidade(texto) == esperado


@pytest.mark.parametrize(
    ("titulo", "esperado"),
    [
        ("Estagiário de Dados", "estagio"),
        ("Data Science Intern", "estagio"),
        ("Analista de Dados Jr", "junior"),
        ("Cientista de Dados Pleno", "pleno"),
        ("Senior Data Scientist", "senior"),
        ("Cientista de Dados Sênior — Crédito", "senior"),
        ("Staff Machine Learning Engineer", "especialista"),
        ("Especialista em IA", "especialista"),
        ("Coordenador(a) de Dados", "gestao"),
        ("Head of Data", "gestao"),
        ("Gerente de Analytics", "gestao"),
        ("Diretor de Dados e IA", "diretoria"),
        ("VP of Engineering", "diretoria"),
        ("Cientista de Dados", None),
    ],
)
def test_senioridade_pelo_titulo(titulo, esperado):
    assert senioridade(titulo) == esperado


def test_idioma_do_texto():
    assert (
        idioma_do_texto("We are looking for a data scientist to join our team and work with the")
        == "en"
    )
    assert (
        idioma_do_texto("Buscamos uma pessoa para atuar com dados e que tenha vontade de") == "pt"
    )


@pytest.mark.parametrize(
    ("texto", "nivel"),
    [
        ("Requisitos: inglês avançado e SQL.", 3),
        ("Inglês fluente é obrigatório.", 4),
        ("Desejável inglês intermediário.", 2),
        ("Fluência em inglês para reuniões globais.", 4),
        ("Fluent English is required.", 4),
        ("Requisitos: Python e SQL.", None),
    ],
)
def test_ingles_exigido(texto, nivel):
    assert ingles_exigido(texto) == nivel


def test_vaga_em_ingles_exige_ingles_profissional():
    texto = "We are looking for a data scientist to join our team and work with the business."
    assert ingles_exigido(texto) == 3


def _idioma(texto: str) -> Fato:
    return Fato(id="F-001", tipo="idioma", texto=texto)


@pytest.mark.parametrize(
    ("texto", "nivel"),
    [
        ("Inglês: avançado", 3),
        ("Inglês: profissional", 3),
        ("English (Full Professional)", 4),
        ("Inglês fluente (C1)", 4),
        ("Inglês: intermediário", 2),
    ],
)
def test_nivel_de_ingles_declarado_no_dossie(texto, nivel):
    assert nivel_ingles_declarado([_idioma("Português: nativo"), _idioma(texto)]) == nivel


def test_sem_ingles_no_dossie():
    assert nivel_ingles_declarado([_idioma("Português: nativo")]) is None


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        (f"Salário: {RS} 12.000", Salario("BRL", Decimal(12000), Decimal(12000))),
        (f"Faixa: {RS} 10.000 a {RS} 14.500,00", Salario("BRL", Decimal(10000), Decimal(14500))),
        (f"{RS} 15k - 18k por mês", Salario("BRL", Decimal(15000), Decimal(18000))),
        (f"{RS} 180.000 por ano", Salario("BRL", Decimal(15000), Decimal(15000))),
        ("US$ 6,000/month", Salario("USD", Decimal(6000), Decimal(6000))),
        (
            "Base salary: $120,000 - $150,000 per year",
            Salario("USD", Decimal(10000), Decimal(12500)),
        ),
        (
            "Annual Salary:\n$190,000—$230,000 USD",
            Salario("USD", Decimal(15833), Decimal(19167)),
        ),
        (f"Remuneração anual: {RS} 240.000", Salario("BRL", Decimal(20000), Decimal(20000))),
        ("Salário compatível com o mercado.", None),
    ],
)
def test_salario(texto, esperado):
    assert ler_salario(texto) == esperado


def test_extrair_metadados_usa_o_estruturado_antes_do_texto():
    meta = extrair_metadados(
        "Cientista de Dados Sênior\nModelo híbrido.",
        estruturado={
            "titulo": "Cientista de Dados Sênior",
            "modalidade": "remoto",
            "local": "Curitiba",
        },
    )
    assert meta.modalidade == "remoto"
    assert meta.local == "Curitiba"
    assert meta.senioridade == "senior"
    assert meta.idioma == "pt"


def test_local_pelo_rotulo():
    meta = extrair_metadados("Vaga de dados\nLocal: São Paulo - SP\nModelo híbrido.")
    assert meta.local == "São Paulo - SP"
