"""Custos em micro-dólares (inteiro), gasto por período e teto diário."""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Engine, func
from sqlmodel import Session, select

from app.ia.erros import TetoAtingido
from app.ia.modelos import ChamadaIA

MICRO = Decimal(1_000_000)


def para_micro_usd(custo: Decimal | None) -> int | None:
    if custo is None:
        return None
    return int((custo * MICRO).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def de_micro_usd(micro: int) -> Decimal:
    return Decimal(micro) / MICRO


@dataclass(frozen=True)
class Gasto:
    micro_usd: int
    chamadas: int
    do_cache: int
    sem_preco: int

    @property
    def usd(self) -> Decimal:
        return de_micro_usd(self.micro_usd)


def _agora_local(agora: datetime | None) -> datetime:
    """Um `agora` com fuso já define o dia; sem fuso (ou ausente), vale o relógio da máquina."""
    if agora is not None and agora.tzinfo is not None:
        return agora
    return (agora or datetime.now()).astimezone()


def gasto_desde(engine: Engine, inicio: datetime) -> Gasto:
    consulta = select(
        func.coalesce(func.sum(ChamadaIA.custo_micro_usd), 0),
        func.count(),
        func.count().filter(ChamadaIA.cache_hit),
        func.count().filter(ChamadaIA.custo_micro_usd.is_(None)),
    ).where(ChamadaIA.criado_em >= inicio)
    with Session(engine) as sessao:
        micro, chamadas, do_cache, sem_preco = sessao.exec(consulta).one()
    return Gasto(micro_usd=micro, chamadas=chamadas, do_cache=do_cache, sem_preco=sem_preco)


def gasto_do_dia(engine: Engine, agora: datetime | None = None) -> Gasto:
    """O dia é o do relógio local, não o dia em UTC."""
    inicio = _agora_local(agora).replace(hour=0, minute=0, second=0, microsecond=0)
    return gasto_desde(engine, inicio)


def gasto_do_mes(engine: Engine, agora: datetime | None = None) -> Gasto:
    inicio = _agora_local(agora).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return gasto_desde(engine, inicio)


def checar_teto(engine: Engine, teto_usd: Decimal, agora: datetime | None = None) -> None:
    gasto = gasto_do_dia(engine, agora)
    if gasto.usd >= teto_usd:
        teto = f"{teto_usd:.2f}".replace(".", ",")
        raise TetoAtingido(
            f"O teto diário de IA deste perfil (US$ {teto}) foi atingido. "
            "As tarefas de IA voltam amanhã, ou aumente o teto na configuração."
        )
