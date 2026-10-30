"""Registro de chamadas em `chamadas_ia`, comum a todos os modos de IA."""

import logging
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session

from app.ia.modelos import ChamadaIA

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResultadoIA[S: BaseModel]:
    saida: S
    chamada: ChamadaIA


def registrar(engine: Engine, chamada: ChamadaIA) -> ChamadaIA:
    with Session(engine, expire_on_commit=False) as sessao:
        sessao.add(chamada)
        sessao.commit()
    log.info(
        "ia tarefa=%s v%s modelo=%s:%s cache=%s sucesso=%s custo_micro_usd=%s ms=%s",
        chamada.tarefa,
        chamada.versao_prompt,
        chamada.provedor,
        chamada.modelo,
        chamada.cache_hit,
        chamada.sucesso,
        chamada.custo_micro_usd,
        chamada.duracao_ms,
    )
    return chamada
