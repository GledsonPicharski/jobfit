"""Comparar textos em código: sem caixa, acentos, espaços e pontuação, mas por palavras inteiras."""

import re

from app.dossie.modelos import sem_acento


def palavras(texto: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", sem_acento(texto).casefold()))


def contem(todo: str, parte: str) -> bool:
    """`parte` aparece em `todo` como sequência de palavras inteiras."""
    parte = palavras(parte)
    return bool(parte) and f" {parte} " in f" {palavras(todo)} "


_NUMERO = re.compile(r"\d+(?:[.,]\d+)*%?")


def numeros(texto: str) -> list[str]:
    """Os números do texto como aparecem ("40%", "2,5", "1.200")."""
    return _NUMERO.findall(texto)


def digitos(numero: str) -> str:
    """Só os dígitos: "2,5" e "2.5" batem; "1.200" e "1200" também."""
    return re.sub(r"\D", "", numero)
