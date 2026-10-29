from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlmodel import Session

from app.db import banco_do_perfil
from app.ia.custos import checar_teto, gasto_do_dia, gasto_do_mes, para_micro_usd
from app.ia.erros import TetoAtingido
from app.ia.modelos import ChamadaIA

BRASILIA = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 10, 29, 10, 0, tzinfo=BRASILIA)


@pytest.mark.parametrize(
    ("custo", "micro"),
    [
        (Decimal("0.00125"), 1250),
        (Decimal("1"), 1_000_000),
        (Decimal("0.0000004"), 0),
        (Decimal("0.0000005"), 1),
        (Decimal("0"), 0),
        (None, None),
    ],
)
def test_para_micro_usd(custo, micro):
    assert para_micro_usd(custo) == micro


def _registrar(engine, quando, micro, *, cache_hit=False):
    with Session(engine) as sessao:
        sessao.add(
            ChamadaIA(
                tarefa="t",
                versao_prompt=1,
                provedor="p",
                modelo="m",
                criado_em=quando,
                custo_micro_usd=micro,
                cache_hit=cache_hit,
            )
        )
        sessao.commit()


def test_gasto_do_dia_usa_o_dia_local():
    engine = banco_do_perfil("ana")
    _registrar(engine, AGORA - timedelta(hours=2), 300_000)
    _registrar(engine, AGORA.replace(hour=0, minute=0), 200_000)  # meia-noite local: hoje
    _registrar(engine, AGORA.replace(hour=0) - timedelta(minutes=1), 900_000)  # ontem
    _registrar(engine, AGORA - timedelta(hours=1), None)  # preço desconhecido
    _registrar(engine, AGORA - timedelta(hours=1), 0, cache_hit=True)

    gasto = gasto_do_dia(engine, agora=AGORA)
    assert gasto.micro_usd == 500_000
    assert gasto.usd == Decimal("0.5")
    assert gasto.chamadas == 4
    assert gasto.do_cache == 1
    assert gasto.sem_preco == 1


def test_gasto_do_mes():
    engine = banco_do_perfil("ana")
    _registrar(engine, AGORA.replace(day=1, hour=0), 100)
    _registrar(engine, AGORA.replace(day=1, hour=0) - timedelta(seconds=1), 999)  # setembro
    assert gasto_do_mes(engine, agora=AGORA).micro_usd == 100


def test_banco_vazio_gasta_zero():
    gasto = gasto_do_dia(banco_do_perfil("ana"))
    assert gasto.micro_usd == 0
    assert gasto.chamadas == 0


def test_teto_bloqueia_quando_atingido():
    engine = banco_do_perfil("ana")
    _registrar(engine, AGORA, 2_000_000)
    with pytest.raises(TetoAtingido, match="2,00"):
        checar_teto(engine, Decimal("2.00"), agora=AGORA)


def test_teto_libera_abaixo_do_limite():
    engine = banco_do_perfil("ana")
    _registrar(engine, AGORA, 1_999_999)
    checar_teto(engine, Decimal("2.00"), agora=AGORA)
