"""Cache de respostas: a mesma tarefa, versão, modelo e entrada não pagam duas vezes."""

import hashlib
import json

from pydantic import BaseModel
from sqlmodel import Session

from app.ia.modelos import CacheIA


def _canonica(entrada: str | BaseModel) -> object:
    return entrada.model_dump(mode="json") if isinstance(entrada, BaseModel) else entrada


def chave_cache(tarefa: str, versao: int, modelo: str, entrada: str | BaseModel) -> str:
    payload = json.dumps(
        {"tarefa": tarefa, "versao": versao, "modelo": modelo, "entrada": _canonica(entrada)},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ler_cache(sessao: Session, chave: str) -> CacheIA | None:
    return sessao.get(CacheIA, chave)


def gravar_cache(
    sessao: Session, chave: str, *, tarefa: str, versao: int, modelo: str, saida_json: str
) -> None:
    sessao.merge(
        CacheIA(
            chave=chave, tarefa=tarefa, versao_prompt=versao, modelo=modelo, saida_json=saida_json
        )
    )
