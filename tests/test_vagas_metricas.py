"""Métricas por portal e lembretes dos portais checados à mão."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session

from app.db import banco_do_perfil
from app.perfis.servico import criar_perfil
from app.vagas.catalogo import carregar_catalogo
from app.vagas.metricas import (
    definir_lembrete,
    lembretes_vencidos,
    marcar_checado,
    metricas_por_portal,
)
from app.vagas.tabelas import Avaliacao, Vaga, VagaOrigem, Varredura

AGORA = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


@pytest.fixture
def engine(pasta_dados):
    criar_perfil(pasta_dados, "Ana Exemplo", "ana")
    return banco_do_perfil("ana")


def _vaga(sessao, portal, *, estado="nova", nota=None, aberta=True, dias=1) -> None:
    vaga = Vaga(
        fonte=portal, texto="x", hash_texto=f"{portal}{estado}{nota}{dias}{aberta}",
        estado=estado, aberta=aberta,
    )  # fmt: skip
    sessao.add(vaga)
    sessao.flush()
    vista = AGORA - timedelta(days=dias)
    sessao.add(VagaOrigem(vaga_id=vaga.id, portal=portal, primeira_vez=vista, ultima_vez=vista))
    if nota is not None:
        sessao.add(Avaliacao(vaga_id=vaga.id, nota=nota, faixa="B"))


def test_metricas_por_portal(engine):
    with Session(engine) as sessao:
        _vaga(sessao, "greenhouse", estado="quero_aplicar", nota=80)
        _vaga(sessao, "greenhouse", estado="avaliada", nota=60, dias=3)
        _vaga(sessao, "greenhouse", aberta=False, dias=40)  # fora das 4 semanas
        _vaga(sessao, "remotive", estado="descartada", nota=40)
        portais = {
            "greenhouse": {
                "trazidas": 10,
                "novas": 3,
                "repetidas": 2,
                "filtradas": 5,
                "antigas": 0,
            },
            "remotive": {"trazidas": 4, "novas": 1, "repetidas": 0, "filtradas": 3, "antigas": 0},
        }
        sessao.add(Varredura(inicio=AGORA, portais=json.dumps(portais), estado="concluida"))
        sessao.commit()

    metricas = {m.portal: m for m in metricas_por_portal(engine, agora=AGORA)}
    gh = metricas["greenhouse"]
    assert gh.vagas == 3
    assert gh.novas_por_semana == 0.5  # 2 vagas nas últimas 4 semanas
    assert gh.passa_filtros == 38  # 3 novas de 8 (as repetidas não contam)
    assert gh.nota_media == 70
    assert gh.quero_aplicar == 1
    assert gh.encerradas == 33
    assert metricas["remotive"].nota_media == 40
    assert next(iter(metricas)) == "greenhouse"  # resultado primeiro


def test_colada_nao_entra_nas_metricas(engine):
    with Session(engine) as sessao:
        _vaga(sessao, "colada", estado="quero_aplicar")
        sessao.commit()
    assert [m.portal for m in metricas_por_portal(engine, agora=AGORA)] == []


def test_lembretes_vencem_pela_frequencia(engine, pasta_dados):
    catalogo = carregar_catalogo(pasta_dados)
    assert lembretes_vencidos(engine, catalogo, agora=AGORA) == []  # sem frequência, sem lembrete

    definir_lembrete(engine, "wellfound", frequencia_dias=7, cadastro="cadastrado")
    [(portal, registro)] = lembretes_vencidos(engine, catalogo, agora=AGORA)
    assert portal.id == "wellfound" and registro.cadastro == "cadastrado"

    marcar_checado(engine, "wellfound", "duas vagas boas", agora=AGORA)
    assert lembretes_vencidos(engine, catalogo, agora=AGORA + timedelta(days=6)) == []
    [(portal, registro)] = lembretes_vencidos(engine, catalogo, agora=AGORA + timedelta(days=7))
    assert registro.observacoes == "duas vagas boas"


def test_portal_local_traz_a_frequencia_sugerida(engine, pasta_dados):
    from app.vagas.catalogo import acrescentar_portal

    acrescentar_portal(pasta_dados, nome="Portal Só Meu", frequencia_dias=3)
    catalogo = carregar_catalogo(pasta_dados)
    assert [p.id for p, _ in lembretes_vencidos(engine, catalogo, agora=AGORA)] == ["portal-so-meu"]
