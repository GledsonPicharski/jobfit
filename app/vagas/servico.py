"""Vagas no banco do perfil: registrar, filtrar, avaliar, ajustar e recalcular a nota."""

import hashlib
import json
from dataclasses import asdict
from decimal import Decimal

from sqlalchemy import Engine
from sqlmodel import Session, select

from app.dossie.filtros import fatos_para_ia
from app.dossie.formato import Documento
from app.dossie.modelos import Fato
from app.ia import executar_detalhado
from app.ia.modelos import ChamadaIA
from app.ia.tarefas import AVALIAR_VAGA, EntradaAvaliacao, FatoParaAvaliar
from app.perfis.modelos import Perfil
from app.textos import palavras
from app.vagas.avaliacao import conferir, requisitos_efetivos
from app.vagas.filtros import ResultadoFiltros, aplicar_filtros
from app.vagas.leitura import VagaBruta
from app.vagas.metadados import Metadados, Salario, extrair_metadados, nivel_ingles_declarado
from app.vagas.nota import Item, calcular_nota, carregar_config
from app.vagas.tabelas import Ajuste, Avaliacao, Vaga

ESTADOS = {"avaliada": "Avaliada", "quero_aplicar": "Quero aplicar", "descartada": "Descartada"}
FAIXAS = ("A", "B", "C", "D")


class ErroVaga(ValueError):
    pass


def hash_texto(texto: str) -> str:
    """O mesmo texto, com outra pontuação ou espaçamento, dá o mesmo hash."""
    return hashlib.sha256(palavras(texto).encode("utf-8")).hexdigest()


# --- vagas ----------------------------------------------------------------------


def registrar_vaga(engine: Engine, bruta: VagaBruta) -> tuple[Vaga, bool]:
    """A vaga e se ela é nova; a mesma URL ou o mesmo texto reabrem a que já existe."""
    hash_ = hash_texto(bruta.texto)
    with Session(engine, expire_on_commit=False) as sessao:
        consulta = select(Vaga).where(Vaga.hash_texto == hash_)
        if bruta.url:
            consulta = select(Vaga).where((Vaga.url == bruta.url) | (Vaga.hash_texto == hash_))
        if existente := sessao.exec(consulta).first():
            return existente, False
        meta = extrair_metadados(bruta.texto, bruta.estruturado)
        salario = meta.salario
        vaga = Vaga(
            url=bruta.url,
            fonte=bruta.fonte,
            titulo=meta.titulo,
            empresa=meta.empresa,
            local=meta.local,
            modalidade=meta.modalidade,
            senioridade=meta.senioridade,
            idioma=meta.idioma,
            ingles=meta.ingles,
            salario=json.dumps({k: str(v) for k, v in asdict(salario).items()})
            if salario
            else None,
            texto=bruta.texto,
            hash_texto=hash_,
        )
        sessao.add(vaga)
        sessao.commit()
        return vaga, True


def obter_vaga(engine: Engine, vaga_id: int) -> Vaga | None:
    with Session(engine, expire_on_commit=False) as sessao:
        return sessao.get(Vaga, vaga_id)


def atualizar_vaga(engine: Engine, vaga_id: int, **campos) -> Vaga:
    with Session(engine, expire_on_commit=False) as sessao:
        vaga = sessao.get(Vaga, vaga_id)
        if vaga is None:
            raise ErroVaga("Vaga não encontrada.")
        for campo, valor in campos.items():
            setattr(vaga, campo, valor)
        sessao.add(vaga)
        sessao.commit()
        return vaga


def metadados_da_vaga(vaga: Vaga) -> Metadados:
    salario = None
    if vaga.salario:
        dados = json.loads(vaga.salario)
        salario = Salario(dados["moeda"], Decimal(dados["minimo"]), Decimal(dados["maximo"]))
    return Metadados(
        titulo=vaga.titulo,
        empresa=vaga.empresa,
        local=vaga.local,
        modalidade=vaga.modalidade,  # type: ignore[arg-type]
        senioridade=vaga.senioridade,  # type: ignore[arg-type]
        idioma=vaga.idioma,
        ingles=vaga.ingles,
        salario=salario,
    )


def filtrar(vaga: Vaga, perfil: Perfil, fatos: list[Fato]) -> ResultadoFiltros:
    meta = metadados_da_vaga(vaga)
    return aplicar_filtros(meta, vaga.texto, perfil.criterios, nivel_ingles_declarado(fatos))


# --- avaliações -----------------------------------------------------------------


def fatos_para_avaliar(fatos: list[Fato]) -> list[FatoParaAvaliar]:
    """Só confirmados e liberados para a IA (regra 5); contato não ajuda a avaliar."""
    return [
        FatoParaAvaliar(
            id=f.id,
            tipo=f.tipo,
            texto=f.texto,
            empresa=f.empresa,
            periodo=f"{f.periodo.inicio or '?'} a {f.periodo.fim or 'atual'}"
            if f.periodo
            else None,
        )
        for f in fatos_para_ia(fatos)
        if f.status == "confirmado" and f.tipo != "contato"
    ]


def ultima_avaliacao(engine: Engine, vaga_id: int) -> Avaliacao | None:
    with Session(engine, expire_on_commit=False) as sessao:
        consulta = select(Avaliacao).where(Avaliacao.vaga_id == vaga_id)
        return sessao.exec(consulta.order_by(Avaliacao.id.desc())).first()


def _versao(doc: Documento) -> int | None:
    versao = doc.metadados.get("versao")
    return versao if isinstance(versao, int) else None


async def avaliar(
    perfil: Perfil, engine: Engine, vaga: Vaga, doc: Documento, *, forcar: bool = False
) -> Avaliacao:
    """Filtros em código; se passar (ou se a pessoa forçar), a IA julga e o código dá a nota.

    Idempotente: com o mesmo dossiê, devolve a avaliação que já existe. No modo manual,
    `executar` levanta `AguardandoResposta` e a resposta volta pelo cache.
    """
    filtros = filtrar(vaga, perfil, doc.fatos)
    barrar = filtros.bloqueada and not forcar
    existente = ultima_avaliacao(engine, vaga.id)
    if existente and existente.versao_dossie == _versao(doc) and existente.bloqueada == barrar:
        return existente

    avaliacao = Avaliacao(
        vaga_id=vaga.id,
        versao_dossie=_versao(doc),
        filtros=json.dumps(asdict(filtros), ensure_ascii=False),
        bloqueada=barrar,
    )
    if not barrar:
        fatos = fatos_para_avaliar(doc.fatos)
        entrada = EntradaAvaliacao(vaga=vaga.texto, fatos=fatos)
        resultado = await executar_detalhado(perfil, AVALIAR_VAGA, entrada, engine=engine)
        requisitos, alertas = conferir(resultado.saida, vaga.texto, {f.id for f in fatos})
        avaliacao.requisitos = json.dumps(requisitos, ensure_ascii=False)
        avaliacao.alertas = json.dumps(alertas, ensure_ascii=False)
        avaliacao.chamada_id = resultado.chamada.id
        avaliacao.versao_prompt = AVALIAR_VAGA.versao
        if not vaga.titulo or not vaga.empresa:
            atualizar_vaga(
                engine,
                vaga.id,
                titulo=vaga.titulo or resultado.saida.titulo,
                empresa=vaga.empresa or resultado.saida.empresa,
            )
    with Session(engine, expire_on_commit=False) as sessao:
        sessao.add(avaliacao)
        sessao.commit()
    return recalcular(engine, avaliacao.id)


def ajustes_da_avaliacao(engine: Engine, avaliacao_id: int) -> list[Ajuste]:
    with Session(engine) as sessao:
        consulta = select(Ajuste).where(Ajuste.avaliacao_id == avaliacao_id)
        return list(sessao.exec(consulta.order_by(Ajuste.id)))


def efetivos(engine: Engine, avaliacao: Avaliacao) -> list[dict]:
    ajustes = [(a.requisito, a.acao, a.fato_id) for a in ajustes_da_avaliacao(engine, avaliacao.id)]
    return requisitos_efetivos(json.loads(avaliacao.requisitos), ajustes)


def recalcular(engine: Engine, avaliacao_id: int) -> Avaliacao:
    """A nota em código, a partir dos julgamentos com os ajustes da pessoa (regra 10)."""
    with Session(engine, expire_on_commit=False) as sessao:
        avaliacao = sessao.get(Avaliacao, avaliacao_id)
        if avaliacao is None:
            raise ErroVaga("Avaliação não encontrada.")
        itens = [
            Item(peso=r["peso"], decisao=r["decisao"], aplica=r["aplica"])
            for r in efetivos(engine, avaliacao)
        ]
        nota = None if avaliacao.bloqueada else calcular_nota(itens, carregar_config())
        avaliacao.nota = nota.valor if nota else None
        avaliacao.faixa = nota.faixa if nota else None
        avaliacao.recomenda = nota.recomenda if nota else None
        sessao.add(avaliacao)
        sessao.commit()
        return avaliacao


def ajustar(
    engine: Engine,
    avaliacao_id: int,
    posicao: int,
    acao: str,
    texto: str | None = None,
    fato_id: str | None = None,
) -> Avaliacao:
    with Session(engine) as sessao:
        avaliacao = sessao.get(Avaliacao, avaliacao_id)
        if avaliacao is None or not 0 <= posicao < len(json.loads(avaliacao.requisitos)):
            raise ErroVaga("Requisito não encontrado nesta avaliação.")
        sessao.add(
            Ajuste(
                avaliacao_id=avaliacao_id,
                requisito=posicao,
                acao=acao,
                texto=texto,
                fato_id=fato_id,
            )
        )
        sessao.commit()
    return recalcular(engine, avaliacao_id)


def desfazer_ajuste(engine: Engine, avaliacao_id: int, posicao: int) -> Avaliacao:
    with Session(engine) as sessao:
        consulta = select(Ajuste).where(
            Ajuste.avaliacao_id == avaliacao_id, Ajuste.requisito == posicao
        )
        for ajuste in sessao.exec(consulta):
            sessao.delete(ajuste)
        sessao.commit()
    return recalcular(engine, avaliacao_id)


def custo_da_avaliacao(engine: Engine, avaliacao: Avaliacao) -> ChamadaIA | None:
    if avaliacao.chamada_id is None:
        return None
    with Session(engine) as sessao:
        return sessao.get(ChamadaIA, avaliacao.chamada_id)


def listar_vagas(engine: Engine) -> list[tuple[Vaga, Avaliacao | None]]:
    with Session(engine, expire_on_commit=False) as sessao:
        vagas = list(sessao.exec(select(Vaga).order_by(Vaga.criado_em.desc(), Vaga.id.desc())))
    return [(v, ultima_avaliacao(engine, v.id)) for v in vagas]
