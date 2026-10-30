from pydantic import BaseModel
from sqlmodel import Session

from app.db import banco_do_perfil
from app.ia.cache import chave_cache, gravar_cache, ler_cache


class Entrada(BaseModel):
    texto: str
    extras: dict[str, int]


def test_chave_estavel_para_mesma_entrada():
    a = chave_cache("t", 1, "anthropic:m", Entrada(texto="vaga", extras={"a": 1, "b": 2}))
    b = chave_cache("t", 1, "anthropic:m", Entrada(texto="vaga", extras={"b": 2, "a": 1}))
    assert a == b
    assert len(a) == 64


def test_chave_muda_com_cada_componente():
    base = chave_cache("t", 1, "anthropic:m", "vaga")
    assert chave_cache("outra", 1, "anthropic:m", "vaga") != base
    assert chave_cache("t", 2, "anthropic:m", "vaga") != base
    assert chave_cache("t", 1, "openrouter:m", "vaga") != base
    assert chave_cache("t", 1, "anthropic:m", "vaga!") != base


def test_chave_com_acentos():
    assert chave_cache("t", 1, "m", "ação — coração") != chave_cache("t", 1, "m", "acao - coracao")


def test_gravar_e_ler():
    engine = banco_do_perfil("ana")
    with Session(engine) as sessao:
        assert ler_cache(sessao, "x") is None
        gravar_cache(sessao, "x", tarefa="t", versao=1, modelo="m", saida_json='{"ok": true}')
        sessao.commit()
    with Session(engine) as sessao:
        assert ler_cache(sessao, "x").saida_json == '{"ok": true}'
