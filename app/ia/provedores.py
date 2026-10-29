from typing import assert_never

from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from app.ia.chaves import ler_chave
from app.ia.erros import ChaveAusente
from app.perfis.modelos import PROVEDORES, Nivel, Perfil


def montar_modelo(perfil: Perfil, nivel: Nivel) -> Model:
    provedor = perfil.ia.provedor
    nome = perfil.ia.modelos[nivel]
    chave = ler_chave(perfil.slug, provedor)
    if not chave:
        raise ChaveAusente(
            f"Nenhuma chave do {PROVEDORES[provedor]} cadastrada para este perfil. "
            "Cadastre a chave na tela de configuração de IA."
        )
    match provedor:
        case "anthropic":
            return AnthropicModel(nome, provider=AnthropicProvider(api_key=chave))
        case "openrouter":
            return OpenRouterModel(
                nome, provider=OpenRouterProvider(api_key=chave, app_title="JobFit")
            )
        case _:
            assert_never(provedor)
