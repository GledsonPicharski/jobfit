"""Qualidade de cada portal, por perfil, e os lembretes dos portais checados à mão.

Seção 7 do plano: volume, aderência aos filtros, nota média, resultado e vagas fantasma.
Até a Fase 5, o resultado conta as vagas marcadas "quero aplicar"; candidaturas,
entrevistas e propostas entram quando houver candidaturas no app.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Engine
from sqlmodel import Session, select

from app.ia.modelos import agora_utc
from app.vagas.catalogo import Catalogo, Portal
from app.vagas.tabelas import Avaliacao, PortalPerfil, Vaga, VagaOrigem, Varredura

JANELA = timedelta(weeks=4)
_RESULTADO = ("quero_aplicar",)  # a Fase 5 acrescenta aplicada, entrevista, proposta


@dataclass
class MetricasPortal:
    portal: str
    vagas: int = 0
    novas_por_semana: float = 0.0
    passa_filtros: int | None = None  # % das vagas trazidas (não repetidas) que passaram
    nota_media: int | None = None
    quero_aplicar: int = 0
    encerradas: int | None = None  # % das vagas do portal que fecharam

    @property
    def desligar(self) -> bool:
        """Muita vaga e nenhum resultado, ou quase nada passa nos filtros."""
        sem_resultado = self.vagas >= 10 and not self.quero_aplicar
        nota_baixa = self.nota_media is not None and self.nota_media < 55
        return sem_resultado and (nota_baixa or (self.passa_filtros or 0) < 10)


def _pct(parte: int, todo: int) -> int | None:
    return round(100 * parte / todo) if todo else None


def metricas_por_portal(engine: Engine, agora: datetime | None = None) -> list[MetricasPortal]:
    agora = agora or agora_utc()
    with Session(engine) as sessao:
        linhas = sessao.exec(
            select(VagaOrigem.portal, VagaOrigem.primeira_vez, Vaga).join(
                Vaga, VagaOrigem.vaga_id == Vaga.id
            )
        ).all()
        notas: dict[int, int] = {}
        for avaliacao in sessao.exec(select(Avaliacao).order_by(Avaliacao.id)):
            if avaliacao.nota is not None:
                notas[avaliacao.vaga_id] = avaliacao.nota  # a última avaliação vale
        varreduras = sessao.exec(select(Varredura.portais)).all()

    metricas: dict[str, MetricasPortal] = {}
    soma_notas: dict[str, list[int]] = {}
    fechadas: dict[str, int] = {}
    for portal, primeira_vez, vaga in linhas:
        if portal == "colada":
            continue
        m = metricas.setdefault(portal, MetricasPortal(portal))
        m.vagas += 1
        if primeira_vez >= agora - JANELA:
            m.novas_por_semana += 1
        if vaga.estado in _RESULTADO:
            m.quero_aplicar += 1
        if vaga.aberta is False:
            fechadas[portal] = fechadas.get(portal, 0) + 1
        if vaga.id in notas:
            soma_notas.setdefault(portal, []).append(notas[vaga.id])

    passaram: dict[str, list[int]] = {}
    for texto in varreduras:
        for portal, r in json.loads(texto).items():
            if portal.startswith("_") or r.get("erro") or r.get("pulado"):
                continue
            consideradas = r["trazidas"] - r["repetidas"] - r.get("antigas", 0)
            total = passaram.setdefault(portal, [0, 0])
            total[0] += r["novas"]
            total[1] += consideradas

    for portal, m in metricas.items():
        m.novas_por_semana = round(m.novas_por_semana / (JANELA.days / 7), 1)
        m.encerradas = _pct(fechadas.get(portal, 0), m.vagas)
        if notas_do_portal := soma_notas.get(portal):
            m.nota_media = round(sum(notas_do_portal) / len(notas_do_portal))
        novas, consideradas = passaram.get(portal, [0, 0])
        m.passa_filtros = _pct(novas, consideradas)
    return sorted(
        metricas.values(), key=lambda m: (-m.quero_aplicar, -(m.nota_media or 0), m.portal)
    )


# --- lembretes ------------------------------------------------------------------


def _registro(sessao: Session, portal: str) -> PortalPerfil:
    return sessao.get(PortalPerfil, portal) or PortalPerfil(portal=portal)


def definir_lembrete(
    engine: Engine,
    portal: str,
    *,
    frequencia_dias: int | None,
    cadastro: str | None = None,
    observacoes: str | None = None,
) -> None:
    with Session(engine) as sessao:
        registro = _registro(sessao, portal)
        registro.frequencia_dias = frequencia_dias or None
        registro.cadastro = cadastro or registro.cadastro
        if observacoes is not None:
            registro.observacoes = observacoes.strip() or None
        sessao.add(registro)
        sessao.commit()


def marcar_checado(
    engine: Engine, portal: str, observacoes: str = "", agora: datetime | None = None
) -> None:
    with Session(engine) as sessao:
        registro = _registro(sessao, portal)
        registro.ultima_checagem = agora or agora_utc()
        if observacoes.strip():
            registro.observacoes = observacoes.strip()
        sessao.add(registro)
        sessao.commit()


def lembretes_vencidos(
    engine: Engine, catalogo: Catalogo, agora: datetime | None = None
) -> list[tuple[Portal, PortalPerfil]]:
    """Os portais checados à mão cuja hora de olhar chegou (com frequência definida)."""
    agora = agora or agora_utc()
    with Session(engine, expire_on_commit=False) as sessao:
        registros = {r.portal: r for r in sessao.exec(select(PortalPerfil))}
    vencidos = []
    for portal in catalogo.lembretes():
        registro = registros.get(portal.id) or PortalPerfil(portal=portal.id)
        dias = registro.frequencia_dias or portal.frequencia_dias
        if registro.desligado or not dias:
            continue
        ultima = registro.ultima_checagem
        if ultima is None or ultima + timedelta(days=dias) <= agora:
            vencidos.append((portal, registro))
    return vencidos
