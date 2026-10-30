import json
from pathlib import Path

import pytest

from app.perfis import servico
from app.perfis.modelos import MODELOS_PADRAO, ConfigIA, Perfil
from app.perfis.servico import ErroPerfil

RAIZ = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("slug", ["ana", "ana-exemplo", "camila2", "a" * 40])
def test_slugs_validos(slug):
    assert servico.validar_slug(slug) == slug


@pytest.mark.parametrize(
    "slug", ["", "../x", "..", "Ana", "CON", "con", "lpt1", "joão", "a b", "-ana", "a" * 41, "a/b"]
)
def test_slugs_invalidos(slug):
    with pytest.raises(ErroPerfil):
        servico.validar_slug(slug)


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("Ana Exemplo", "ana-exemplo"),
        ("João  Conceição", "joao-conceicao"),
        ("  Camila!! ", "camila"),
    ],
)
def test_slug_de_nome(nome, esperado):
    assert servico.slug_de_nome(nome) == esperado


def test_criar_listar_carregar(pasta_dados):
    criado = servico.criar_perfil(pasta_dados, "Ana Exemplo")

    assert criado.slug == "ana-exemplo"
    pasta = pasta_dados / "perfis" / "ana-exemplo"
    for sub in ("historico", "fontes", "cvs"):
        assert (pasta / sub).is_dir()
    assert servico.carregar_perfil(pasta_dados, "ana-exemplo") == criado
    assert [p.slug for p in servico.listar_perfis(pasta_dados)] == ["ana-exemplo"]


def test_perfil_duplicado_da_erro(pasta_dados):
    servico.criar_perfil(pasta_dados, "Ana")
    with pytest.raises(ErroPerfil, match="já existe"):
        servico.criar_perfil(pasta_dados, "Outra Ana", slug="ana")


def test_carregar_perfil_inexistente(pasta_dados):
    with pytest.raises(ErroPerfil, match="não encontrado"):
        servico.carregar_perfil(pasta_dados, "ninguem")


def test_listar_ignora_pasta_sem_perfil_valido(pasta_dados):
    servico.criar_perfil(pasta_dados, "Ana")
    (pasta_dados / "perfis" / "lixo").mkdir()
    (pasta_dados / "perfis" / "quebrado").mkdir()
    (pasta_dados / "perfis" / "quebrado" / "perfil.json").write_text("{", encoding="utf-8")
    assert [p.slug for p in servico.listar_perfis(pasta_dados)] == ["ana"]


def test_listar_sem_pasta_de_perfis(tmp_path):
    assert servico.listar_perfis(tmp_path / "vazia") == []


def test_perfil_json_nao_guarda_chave(pasta_dados):
    servico.criar_perfil(pasta_dados, "Ana")
    bruto = (pasta_dados / "perfis" / "ana" / "perfil.json").read_text(encoding="utf-8")
    assert "chave" not in bruto.lower()
    assert "api_key" not in bruto.lower()


def test_trocar_provedor_troca_modelos_padrao():
    ia = ConfigIA()
    nova = ia.com_provedor("openrouter")
    assert nova.modelos == MODELOS_PADRAO["openrouter"]


def test_trocar_provedor_mantem_modelos_personalizados():
    ia = ConfigIA().com_provedor("anthropic")
    ia.modelos["barato"] = "meu-modelo"
    nova = ia.com_provedor("openrouter")
    assert nova.modelos["barato"] == "meu-modelo"
    assert nova.modelos["forte"] == MODELOS_PADRAO["openrouter"]["forte"]


def test_perfil_novo_nasce_no_modo_manual_sem_chave():
    ia = ConfigIA()
    assert ia.provedor == "manual"
    assert not ia.precisa_chave
    assert ia.com_provedor("anthropic").modelos == MODELOS_PADRAO["anthropic"]
    assert ia.com_provedor("anthropic").precisa_chave


def test_perfil_ficticio_do_repositorio_e_valido():
    bruto = (RAIZ / "exemplos" / "perfil-ficticio" / "perfil.json").read_text(encoding="utf-8")
    perfil = Perfil.model_validate(json.loads(bruto))
    assert servico.validar_slug(perfil.slug) == perfil.slug
