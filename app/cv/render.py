"""O PDF do CV: template HTML de uma coluna (legível por ATS) e Chromium pelo Playwright.

O Playwright roda na API síncrona, numa thread própria: assim não depende do laço de
eventos do servidor (no Windows, o do uvicorn pode não aceitar subprocessos). Depois de
gerado, o PDF é relido com `pdfplumber` para conferir páginas e a ordem do texto.
"""

import io
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.cv.modelos import Rascunho

PASTA_TEMPLATES = Path(__file__).parent / "templates"
MAXIMO_PAGINAS = 2
TITULOS_SECAO = {
    "pt": {
        "resumo": "Resumo",
        "experiencias": "Experiência",
        "competencias": "Competências",
        "formacao": "Formação",
        "idiomas": "Idiomas",
        "certificacoes": "Certificações",
        "outros": "Prêmios, publicações e docência",
    },
    "en": {
        "resumo": "Summary",
        "experiencias": "Experience",
        "competencias": "Skills",
        "formacao": "Education",
        "idiomas": "Languages",
        "certificacoes": "Certifications",
        "outros": "Awards, publications and teaching",
    },
}
_ambiente = Environment(
    loader=FileSystemLoader(PASTA_TEMPLATES), autoescape=select_autoescape(["html"])
)


class ErroPDF(RuntimeError):
    pass


@dataclass(frozen=True)
class PDF:
    conteudo: bytes
    paginas: int
    texto: str


def html_do_cv(
    rascunho: Rascunho,
    nome: str,
    contato: list[str],
    linhas: list[tuple[str | None, str]],
    titulos: dict[str, str],
) -> str:
    """`linhas`: empresa e período de cada experiência, renderizados pelo código."""
    return _ambiente.get_template("cv.html").render(
        r=rascunho, nome=nome, contato=contato, linhas=linhas, titulos=titulos
    )


def _imprimir(html: str) -> bytes:
    from playwright.sync_api import Error, sync_playwright  # lento para importar

    try:
        with sync_playwright() as p:
            navegador = p.chromium.launch()
            try:
                pagina = navegador.new_page()
                pagina.set_content(html, wait_until="load")
                return pagina.pdf(format="A4", prefer_css_page_size=True, print_background=True)
            finally:
                navegador.close()
    except Error as erro:
        if "Executable doesn't exist" in str(erro):
            raise ErroPDF(
                "O Chromium do Playwright não está instalado. Rode uma vez: "
                "uv run playwright install chromium"
            ) from erro
        raise ErroPDF(f"O Chromium não conseguiu gerar o PDF ({type(erro).__name__}).") from erro


def conferir(conteudo: bytes) -> tuple[int, str]:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        return len(pdf.pages), "\n".join(p.extract_text() or "" for p in pdf.pages)


async def gerar_pdf(html: str) -> PDF:
    import anyio

    conteudo = await anyio.to_thread.run_sync(_imprimir, html)
    paginas, texto = conferir(conteudo)
    return PDF(conteudo, paginas, texto)
