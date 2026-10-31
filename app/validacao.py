"""Erros do Pydantic em português, para a tela (resposta colada, dossiê editado à mão)."""

from typing import Any

ERROS_PYDANTIC = {
    "missing": "campo obrigatório ausente",
    "string_too_long": "texto longo demais",
    "string_too_short": "texto vazio",
    "string_type": "deveria ser um texto",
    "string_pattern_mismatch": "formato inválido",
    "bool_parsing": "deveria ser true ou false",
    "bool_type": "deveria ser true ou false",
    "int_parsing": "deveria ser um número inteiro",
    "int_type": "deveria ser um número inteiro",
    "float_parsing": "deveria ser um número",
    "list_type": "deveria ser uma lista",
    "dict_type": "deveria ser um objeto",
    "model_type": "deveria ser um objeto",
    "literal_error": "valor fora das opções permitidas",
    "extra_forbidden": "campo não esperado",
}


def descrever_erro(erro: Any, raiz: str = "resposta") -> str:
    campo = ".".join(str(parte) for parte in erro["loc"]) or raiz
    if erro["type"] == "value_error":  # mensagem nossa, de um field_validator
        return f"{campo}: {erro['msg'].removeprefix('Value error, ')}"
    return f"{campo}: {ERROS_PYDANTIC.get(erro['type'], erro['msg'])}"
