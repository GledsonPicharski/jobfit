from datetime import datetime

import pytest
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openrouter import OpenRouterModel

from app.ia import chaves
from app.ia.erros import ChaveAusente
from app.ia.provedores import montar_modelo
from app.perfis.modelos import ConfigIA, Perfil


def _perfil(provedor):
    return Perfil(
        slug="ana", nome="Ana", criado_em=datetime.now(), ia=ConfigIA().com_provedor(provedor)
    )


def test_sem_chave_da_erro_claro():
    with pytest.raises(ChaveAusente, match="Anthropic"):
        montar_modelo(_perfil("anthropic"), "barato")


@pytest.mark.parametrize(
    ("provedor", "classe", "nome"),
    [
        ("anthropic", AnthropicModel, "claude-haiku-5-5"),
        ("openrouter", OpenRouterModel, "anthropic/claude-haiku-5.5"),
    ],
)
def test_monta_modelo_do_provedor(provedor, classe, nome):
    chaves.salvar_chave("ana", provedor, "chave-de-teste")
    modelo = montar_modelo(_perfil(provedor), "barato")
    assert isinstance(modelo, classe)
    assert modelo.model_name == nome


def test_usa_a_chave_do_perfil_certo():
    chaves.salvar_chave("camila", "anthropic", "chave-da-camila")
    with pytest.raises(ChaveAusente):
        montar_modelo(_perfil("anthropic"), "barato")
