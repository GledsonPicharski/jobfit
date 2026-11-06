import pytest

from app.cv.modelos import Experiencia, Frase, Rascunho
from app.cv.render import TITULOS_SECAO, gerar_pdf, html_do_cv

pytestmark = pytest.mark.anyio

RASCUNHO = Rascunho(
    idioma="pt",
    titulo=Frase(texto="Gerente de Dados e IA", fatos=["F-010"]),
    resumo=[Frase(texto="Lidera produtos de IA — da descoberta à operação.", fatos=["F-040"])],
    experiencias=[
        Experiencia(
            cargo_id="F-010",
            titulo="Gerente de Dados e IA",
            bullets=[
                Frase(texto="Automatizou mais de 80% das leituras de documentos.", fatos=["F-014"])
            ],
        ),
        Experiencia(cargo_id="F-020", titulo="Analista de Dados Sênior"),
    ],
    competencias=[
        Frase(texto="Python", fatos=["F-041"]),
        Frase(texto="Gestão de produtos", fatos=["F-040"]),
    ],
    formacao=[Frase(texto="Bacharelado em Estatística — 2014", fatos=["F-030"])],
)
LINHAS = [("Empresa Exemplo", "mar 2023 – atual"), ("Consultoria Fictícia", "jan 2018 – fev 2023")]


def _html(rascunho=RASCUNHO):
    return html_do_cv(
        rascunho, "Ana Exemplo", ["São Paulo", "linkedin.com/in/ana"], LINHAS, TITULOS_SECAO["pt"]
    )


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_html_tem_a_estrutura_de_um_cv_ats():
    html = _html()
    assert "<table" not in html and "<img" not in html
    assert "<h1>Ana Exemplo</h1>" in html
    assert "São Paulo | linkedin.com/in/ana" in html
    assert "Empresa Exemplo | mar 2023 – atual" in html
    assert "Python · Gestão de produtos" in html
    assert html.index("Experiência") < html.index("Competências") < html.index("Formação")


def test_html_escapa_o_texto():
    rascunho = RASCUNHO.model_copy(deep=True)
    rascunho.resumo[0].texto = "<script>alert(1)</script> & cia"
    html = _html(rascunho)
    assert "<script>alert" not in html and "&lt;script&gt;" in html


def test_secao_vazia_nao_aparece():
    assert "Certificações" not in _html()


async def test_pdf_tem_texto_selecionavel_na_ordem_e_com_acentos(chromium):
    pdf = await gerar_pdf(_html())
    assert pdf.conteudo.startswith(b"%PDF")
    assert pdf.paginas == 1
    texto = pdf.texto
    for trecho in ("Ana Exemplo", "Estatística", "ação", "—", "mais de 80%"):
        assert trecho in texto
    ordem = [
        "Ana Exemplo",
        "Resumo",
        "Gerente de Dados e IA",
        "Analista de Dados Sênior",
        "Formação",
    ]
    posicao = 0
    for trecho in ordem:  # cada um depois do anterior: o texto copiado mantém a ordem
        posicao = texto.index(trecho, posicao) + len(trecho)
