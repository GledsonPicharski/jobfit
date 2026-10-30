import pytest
from sqlmodel import Session, select

from app import config
from app.db import banco_do_perfil
from app.ia.chaves import salvar_chave, tem_chave
from app.ia.modelos import ChamadaIA
from app.perfis.exclusao import excluir_perfil
from app.perfis.servico import ErroPerfil, criar_perfil, listar_perfis, pasta_perfil


@pytest.fixture
def ana(pasta_dados):
    perfil = criar_perfil(pasta_dados, "Ana Exemplo", "ana")
    with Session(banco_do_perfil("ana")) as sessao:
        sessao.add(ChamadaIA(tarefa="t", versao_prompt=1, provedor="manual", modelo="chat"))
        sessao.commit()
    return perfil


def test_move_a_pasta_do_perfil_para_a_lixeira(pasta_dados, ana):
    (pasta_perfil(pasta_dados, "ana") / "fontes" / "Currículo – ação.md").write_text(
        "conteúdo com ç", encoding="utf-8"
    )

    destino = excluir_perfil(pasta_dados, "ana")

    assert destino.parent == pasta_dados / "lixeira"
    assert destino.name.startswith("ana-")
    assert not pasta_perfil(pasta_dados, "ana").exists()
    assert (destino / "perfil.json").is_file()
    texto = (destino / "fontes" / "Currículo – ação.md").read_text(encoding="utf-8")
    assert texto == "conteúdo com ç"
    assert listar_perfis(pasta_dados) == []


def test_banco_vai_junto_para_a_lixeira(pasta_dados, ana):
    destino = excluir_perfil(pasta_dados, "ana")

    assert not config.caminho_banco("ana").exists()
    assert (destino / "banco.db").is_file()


def test_apaga_as_chaves_so_do_perfil_excluido(pasta_dados, ana):
    criar_perfil(pasta_dados, "Bia", "bia")
    salvar_chave("ana", "anthropic", "sk-ana")
    salvar_chave("ana", "openrouter", "sk-or-ana")
    salvar_chave("bia", "anthropic", "sk-bia")

    excluir_perfil(pasta_dados, "ana")

    assert not tem_chave("ana", "anthropic")
    assert not tem_chave("ana", "openrouter")
    assert tem_chave("bia", "anthropic")


def test_esquece_o_ultimo_perfil_se_era_o_excluido(pasta_dados, ana):
    cfg = config.carregar_config()
    config.salvar_config(cfg.model_copy(update={"ultimo_perfil": "ana"}))

    excluir_perfil(pasta_dados, "ana")

    assert config.carregar_config().ultimo_perfil is None


def test_mantem_o_ultimo_perfil_se_era_outro(pasta_dados, ana):
    criar_perfil(pasta_dados, "Bia", "bia")
    cfg = config.carregar_config()
    config.salvar_config(cfg.model_copy(update={"ultimo_perfil": "bia"}))

    excluir_perfil(pasta_dados, "ana")

    assert config.carregar_config().ultimo_perfil == "bia"


def test_recriar_com_o_mesmo_nome_comeca_do_zero(pasta_dados, ana):
    excluir_perfil(pasta_dados, "ana")
    criar_perfil(pasta_dados, "Ana Exemplo", "ana")

    with Session(banco_do_perfil("ana")) as sessao:
        assert sessao.exec(select(ChamadaIA)).all() == []


def test_excluir_duas_vezes_o_mesmo_slug_nao_sobrescreve_a_lixeira(pasta_dados, ana):
    primeira = excluir_perfil(pasta_dados, "ana")
    criar_perfil(pasta_dados, "Ana Exemplo", "ana")
    segunda = excluir_perfil(pasta_dados, "ana")

    assert primeira != segunda
    assert primeira.is_dir()
    assert segunda.is_dir()


def test_perfil_sem_banco_tambem_e_excluido(pasta_dados):
    criar_perfil(pasta_dados, "Bia", "bia")
    destino = excluir_perfil(pasta_dados, "bia")
    assert (destino / "perfil.json").is_file()
    assert not (destino / "banco.db").exists()


@pytest.mark.parametrize("slug", ["ninguem", "../x"])
def test_perfil_inexistente_ou_invalido_da_erro(pasta_dados, slug):
    with pytest.raises(ErroPerfil):
        excluir_perfil(pasta_dados, slug)
