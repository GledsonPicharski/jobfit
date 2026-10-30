import logging

import pytest

from app.ia import chaves

CHAVE = "sk-ant-teste-123456789"


def test_salvar_ler_apagar(chaveiro):
    assert chaves.ler_chave("ana", "anthropic") is None
    chaves.salvar_chave("ana", "anthropic", f"  {CHAVE}\n")

    assert chaves.ler_chave("ana", "anthropic") == CHAVE
    assert chaveiro.segredos == {("jobfit", "ana:anthropic"): CHAVE}
    assert chaves.tem_chave("ana", "anthropic")
    assert not chaves.tem_chave("ana", "openrouter")
    assert not chaves.tem_chave("camila", "anthropic")

    chaves.apagar_chave("ana", "anthropic")
    assert chaves.ler_chave("ana", "anthropic") is None
    chaves.apagar_chave("ana", "anthropic")  # apagar de novo não dá erro


def test_chave_vazia_e_recusada():
    with pytest.raises(ValueError, match="vazia"):
        chaves.salvar_chave("ana", "anthropic", "   ")


def test_chave_nao_vaza_em_log_nem_em_arquivo(caplog, pasta_dados, tmp_path):
    from app.perfis.servico import criar_perfil

    caplog.set_level(logging.DEBUG)
    criar_perfil(pasta_dados, "Ana")
    chaves.salvar_chave("ana", "anthropic", CHAVE)
    chaves.ler_chave("ana", "anthropic")

    assert CHAVE not in caplog.text
    for arquivo in tmp_path.rglob("*"):
        if arquivo.is_file():
            assert CHAVE.encode() not in arquivo.read_bytes(), arquivo
