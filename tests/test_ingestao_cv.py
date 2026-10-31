import io
import zipfile

import pytest
from fpdf import FPDF

from app.ingestao.cv import ErroCV, texto_do_cv
from tests.cv_ficticio import LINHAS, gerar_cv_docx, gerar_cv_pdf


def test_pdf_vira_texto_com_acento():
    texto = texto_do_cv(gerar_cv_pdf())
    assert "Gerente de Dados - Empresa Exemplo (nov/2022 - atual)" in texto
    assert "ação contínua" in texto


def test_pdf_com_varias_paginas_mantem_a_ordem():
    texto = texto_do_cv(gerar_cv_pdf(paginas=2))
    assert texto.index("ação contínua.") < texto.index("(p2)")


def test_docx_com_paragrafos_e_tabela():
    texto = texto_do_cv(gerar_cv_docx(tabela=["Python", "SQL — avançado"]))
    assert texto.splitlines()[:2] == LINHAS[:2]
    assert "Python | SQL — avançado" in texto


def test_pdf_sem_texto_selecionavel():
    pdf = FPDF()
    pdf.add_page()
    with pytest.raises(ErroCV, match="imagem"):
        texto_do_cv(bytes(pdf.output()))


def test_doc_antigo_e_outros_arquivos():
    with pytest.raises(ErroCV, match=r"\.docx"):
        texto_do_cv(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 100)  # .doc do Word 97
    with pytest.raises(ErroCV, match="PDF ou DOCX"):
        texto_do_cv(b"texto qualquer")
    with pytest.raises(ErroCV, match="PDF ou DOCX"):
        zip_qualquer = io.BytesIO()
        with zipfile.ZipFile(zip_qualquer, "w") as z:
            z.writestr("a.txt", "oi")
        texto_do_cv(zip_qualquer.getvalue())
    with pytest.raises(ErroCV, match="PDF"):
        texto_do_cv(b"%PDF-1.4 quebrado")
