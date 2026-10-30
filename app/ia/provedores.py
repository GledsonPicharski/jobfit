from typing import TYPE_CHECKING, assert_never

from app.ia.chaves import ler_chave
from app.ia.erros import ChaveAusente
from app.perfis.modelos import PROVEDORES, Nivel, Perfil

if TYPE_CHECKING:
    from pydantic_ai.models import Model


def montar_modelo(perfil: Perfil, nivel: Nivel) -> "Model":
    provedor = perfil.ia.provedor
    if provedor == "manual":
        raise ValueError("O modo manual não usa modelo de API; executar() trata antes.")
    nome = perfil.ia.modelos[nivel]
    chave = ler_chave(perfil.slug, provedor)
    if not chave:
        raise ChaveAusente(
            f"Nenhuma chave do {PROVEDORES[provedor]} cadastrada para este perfil. "
            "Cadastre a chave na tela de configuração de IA."
        )
    # Os SDKs dos provedores levam segundos para importar no Windows; só carregam
    # na primeira chamada de IA, para o app abrir rápido.
    match provedor:
        case "anthropic":
            from pydantic_ai.models.anthropic import AnthropicModel
            from pydantic_ai.providers.anthropic import AnthropicProvider

            return AnthropicModel(nome, provider=AnthropicProvider(api_key=chave))
        case "openrouter":
            from pydantic_ai.models.openrouter import OpenRouterModel
            from pydantic_ai.providers.openrouter import OpenRouterProvider

            return OpenRouterModel(
                nome, provider=OpenRouterProvider(api_key=chave, app_title="JobFit")
            )
        case _:
            assert_never(provedor)
