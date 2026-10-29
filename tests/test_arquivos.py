import os

import pytest

from app.arquivos import gravar_texto, ler_texto

TEXTO = "Gestão de dados — ação, coração e ç/ã/é/ü 🚀\nsegunda linha\n"


def test_ida_e_volta_preserva_acentos(tmp_path):
    caminho = tmp_path / "Meu Drive" / "Currículo – teste" / "nota.md"
    gravar_texto(caminho, TEXTO)
    assert ler_texto(caminho) == TEXTO


def test_grava_utf8_sem_bom_e_com_lf(tmp_path):
    caminho = tmp_path / "nota.md"
    gravar_texto(caminho, TEXTO)
    bruto = caminho.read_bytes()
    assert not bruto.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in bruto
    assert bruto.decode("utf-8") == TEXTO


def test_falha_na_gravacao_preserva_original_e_nao_deixa_temporario(tmp_path, monkeypatch):
    caminho = tmp_path / "dossie.md"
    gravar_texto(caminho, "versão original")

    def falhar(*_args):
        raise OSError("disco cheio")

    monkeypatch.setattr(os, "replace", falhar)
    with pytest.raises(OSError):
        gravar_texto(caminho, "versão nova")

    assert ler_texto(caminho) == "versão original"
    assert [p.name for p in tmp_path.iterdir()] == ["dossie.md"]
