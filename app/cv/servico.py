"""CV por vaga: seleção (código) → redação (IA) → rascunho conferido (código) → PDF."""

import json
from datetime import date
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, select

from app.cv.checagem import Checagem, checar, limpar_ids
from app.cv.modelos import CVRedigido, Experiencia, Idioma, Rascunho
from app.cv.selecao import ConfigCV, Selecao, carregar_config, periodo_legivel, selecionar
from app.cv.tabelas import CV
from app.dossie.filtros import fatos_publicaveis
from app.dossie.formato import Documento
from app.dossie.modelos import Fato
from app.dossie.versoes import alterar_dossie
from app.ia import executar_detalhado
from app.ia.modelos import ChamadaIA, agora_utc
from app.ia.tarefas import REDIGIR_CV, CargoParaCV, EntradaCV, FatoParaCV
from app.perfis.modelos import Perfil
from app.vagas.servico import efetivos, ultima_avaliacao
from app.vagas.tabelas import Vaga


class ErroCV(ValueError):
    pass


def _extra(fato: Fato, campo: str) -> str | None:
    valor = (fato.model_extra or {}).get(campo)
    return str(valor) if valor else None


def _periodo(fato: Fato) -> str | None:
    if fato.periodo is None:
        return None
    return f"{fato.periodo.inicio or '?'} a {fato.periodo.fim or 'atual'}"


def citados_na_avaliacao(engine: Engine, vaga: Vaga | None) -> set[str]:
    """Os fatos que a avaliação usou em "atende" ou "parcial": os mais relevantes."""
    if vaga is None or (avaliacao := ultima_avaliacao(engine, vaga.id)) is None:
        return set()
    return {
        f
        for r in efetivos(engine, avaliacao)
        if r["aplica"] and r["decisao"] in ("atende", "parcial")
        for f in r["fatos"]
    }


def montar_entrada(
    selecao: Selecao, idioma: Idioma, vaga: str | None, config: ConfigCV
) -> EntradaCV:
    fatos = [
        FatoParaCV(
            id=f.id,
            tipo=f.tipo,
            texto=f.texto,
            texto_en=_extra(f, "texto_en"),
            empresa=f.empresa,
            periodo=_periodo(f),
            metricas=f.metricas,
        )
        for f in selecao.para_ia
    ]
    cargos = [
        CargoParaCV(
            cargo_id=c.cargo.id,
            cargo=c.cargo.cargo or c.cargo.texto,
            cargo_en=_extra(c.cargo, "cargo_en"),
            empresa=c.cargo.empresa,
            periodo=_periodo(c.cargo),
            fatos=[f.id for f in c.fatos],
        )
        for c in selecao.cargos
    ]
    return EntradaCV(
        idioma=idioma,
        vaga=vaga,
        cargos=cargos,
        fatos=fatos,
        frases_resumo=config.frases_resumo,
        bullets_por_cargo=config.bullets_por_cargo,
        competencias=config.competencias,
    )


def titulo_do_cargo(cargo: Fato, idioma: Idioma, traduzido: str | None) -> str:
    original = cargo.cargo or cargo.texto
    if idioma == "pt":
        return original
    return _extra(cargo, "cargo_en") or traduzido or original


def montar_rascunho(
    redigido: CVRedigido, selecao: Selecao, idioma: Idioma
) -> tuple[Rascunho, list[str]]:
    """A ordem e os cargos são do código; as frases, da IA, sem IDs que não foram enviados."""
    por_cargo = {e.cargo_id: e for e in redigido.experiencias}
    experiencias = []
    for c in selecao.cargos:
        escrito = por_cargo.get(c.cargo.id)
        traduzido = escrito.cargo_traduzido if escrito else None
        experiencias.append(
            Experiencia(
                cargo_id=c.cargo.id,
                titulo=titulo_do_cargo(c.cargo, idioma, traduzido),
                bullets=escrito.bullets if escrito and c.detalhado else [],
            )
        )
    rascunho = Rascunho(
        idioma=idioma,
        titulo=redigido.titulo,
        resumo=redigido.resumo,
        experiencias=experiencias,
        competencias=redigido.competencias,
        formacao=redigido.formacao,
        idiomas=redigido.idiomas,
        certificacoes=redigido.certificacoes,
        outros=redigido.outros,
    )
    return limpar_ids(rascunho, {f.id for f in selecao.para_ia})


def _versao(doc: Documento) -> int | None:
    versao = doc.metadados.get("versao")
    return versao if isinstance(versao, int) else None


def cvs_da_vaga(engine: Engine, vaga_id: int) -> list[CV]:
    with Session(engine) as sessao:
        consulta = select(CV).where(CV.vaga_id == vaga_id).order_by(CV.id.desc())
        return list(sessao.exec(consulta))


def obter_cv(engine: Engine, cv_id: int) -> CV | None:
    with Session(engine, expire_on_commit=False) as sessao:
        return sessao.get(CV, cv_id)


async def gerar(
    perfil: Perfil,
    engine: Engine,
    doc: Documento,
    vaga: Vaga | None,
    idioma: Idioma,
    hoje: date | None = None,
) -> CV:
    """Idempotente: com o mesmo dossiê, devolve o rascunho que já existe para a vaga e idioma.

    No modo manual, `executar` levanta `AguardandoResposta` e a resposta volta pelo cache.
    """
    if vaga is not None:
        for existente in cvs_da_vaga(engine, vaga.id):
            if existente.idioma == idioma and existente.versao_dossie == _versao(doc):
                return existente
    config = carregar_config()
    citados = citados_na_avaliacao(engine, vaga)
    selecao = selecionar(
        doc.fatos, vaga.texto if vaga else None, citados, config, hoje or date.today()
    )
    if not selecao.cargos:
        raise ErroCV("O dossiê ainda não tem cargos confirmados para montar um CV.")
    entrada = montar_entrada(selecao, idioma, vaga.texto if vaga else None, config)
    resultado = await executar_detalhado(perfil, REDIGIR_CV, entrada, engine=engine)
    rascunho, removidos = montar_rascunho(resultado.saida, selecao, idioma)
    alertas = []
    if removidos:
        alertas.append(
            f"A IA citou fatos que não foram enviados, e eles saíram: {', '.join(removidos)}."
        )
    cv = CV(
        vaga_id=vaga.id if vaga else None,
        idioma=idioma,
        conteudo=rascunho.model_dump_json(),
        alertas=json.dumps(alertas, ensure_ascii=False),
        versao_dossie=_versao(doc),
        chamada_id=resultado.chamada.id,
        versao_prompt=REDIGIR_CV.versao,
    )
    with Session(engine, expire_on_commit=False) as sessao:
        sessao.add(cv)
        sessao.commit()
    return cv


def rascunho_do_cv(cv: CV) -> Rascunho:
    return Rascunho.model_validate_json(cv.conteudo)


def fatos_para_checar(doc: Documento) -> dict[str, Fato]:
    """Só publicáveis: uma frase nunca se sustenta num fato 🔒 (regra 5)."""
    return {f.id: f for f in fatos_publicaveis(doc.fatos)}


def checar_cv(cv: CV, doc: Documento, vaga: Vaga | None) -> Checagem:
    return checar(
        rascunho_do_cv(cv), fatos_para_checar(doc), empresa_vaga=vaga.empresa if vaga else None
    )


def salvar_rascunho(engine: Engine, cv_id: int, rascunho: Rascunho) -> CV:
    """Uma edição invalida o PDF anterior: ele precisa ser gerado de novo."""
    with Session(engine, expire_on_commit=False) as sessao:
        cv = sessao.get(CV, cv_id)
        if cv is None:
            raise ErroCV("CV não encontrado.")
        cv.conteudo = rascunho.model_dump_json()
        cv.estado = "rascunho"
        cv.atualizado_em = agora_utc()
        sessao.add(cv)
        sessao.commit()
        return cv


def confirmar_traducao(
    pasta_dados: Path, engine: Engine, perfil: Perfil, cargo_id: str, traducao: str
) -> None:
    """A tradução que a pessoa confirma vira `cargo_en` no fato (decisão 0007)."""

    def gravar(doc: Documento) -> None:
        try:
            fato = doc.fato(cargo_id)
        except KeyError as erro:
            raise ErroCV(f"O cargo {cargo_id} não está no dossiê.") from erro
        doc.substituir_fato(fato.model_copy(update={"cargo_en": traducao.strip()}))

    alterar_dossie(pasta_dados, engine, perfil, "edicao_app", gravar)


def linhas_do_cargo(cargo: Fato, idioma: Idioma) -> tuple[str | None, str]:
    """Empresa e período, como o código renderiza (nunca vêm da IA)."""
    return cargo.empresa, periodo_legivel(cargo, idioma)


def selecionar_contato(doc: Documento) -> list[Fato]:
    """Contato publicável para o cabeçalho: vem do dossiê, renderizado localmente."""
    return [f for f in fatos_publicaveis(doc.fatos) if f.tipo == "contato"]


def custo(engine: Engine, cv: CV) -> ChamadaIA | None:
    if cv.chamada_id is None:
        return None
    with Session(engine) as sessao:
        return sessao.get(ChamadaIA, cv.chamada_id)
