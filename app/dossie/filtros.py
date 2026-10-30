"""Regra 5 do CLAUDE.md, em código: todo caminho para a IA ou para fora passa por aqui."""

from collections.abc import Iterable

from app.dossie.modelos import Fato


def fatos_para_ia(fatos: Iterable[Fato]) -> list[Fato]:
    """O que pode ir ao provedor de IA (ou ao chat, no modo manual)."""
    return [f for f in fatos if not f.nao_enviar_ia]


def fatos_publicaveis(fatos: Iterable[Fato]) -> list[Fato]:
    """O que pode ir para CV, LinkedIn ou e-mail: confirmado e sem 🔒."""
    return [f for f in fatos if f.status == "confirmado" and not f.privado]
