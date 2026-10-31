"""Comparar textos em código: sem caixa, acentos, espaços e pontuação, mas por palavras inteiras."""

import re

from app.dossie.modelos import sem_acento


def palavras(texto: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", sem_acento(texto).casefold()))


def contem(todo: str, parte: str) -> bool:
    """`parte` aparece em `todo` como sequência de palavras inteiras."""
    parte = palavras(parte)
    return bool(parte) and f" {parte} " in f" {palavras(todo)} "
