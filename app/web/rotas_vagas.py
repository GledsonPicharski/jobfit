"""Vagas: critérios (filtros duros), avaliação, forças e lacunas."""

import json
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from app.db import banco_do_perfil
from app.dossie.formato import ErroDossie
from app.dossie.modelos import ROTULOS_TIPO
from app.dossie.versoes import carregar_dossie
from app.ia import ErroIA
from app.perfis.modelos import Criterios, Perfil
from app.perfis.servico import salvar_perfil
from app.vagas import servico
from app.vagas.avaliacao import ACOES
from app.vagas.leitura import ErroLeituraVaga, ler_texto, ler_url
from app.vagas.metadados import MODALIDADES, NIVEIS_INGLES, SENIORIDADES
from app.vagas.tabelas import Vaga
from app.validacao import descrever_erro
from app.web.formatos import ler_decimal
from app.web.rotas import Pasta, PerfilAtual, ir, templates

router = APIRouter()
templates.env.globals.update(
    MODALIDADES=MODALIDADES,
    SENIORIDADES=SENIORIDADES,
    NIVEIS_INGLES=NIVEIS_INGLES,
    ESTADOS_VAGA=servico.ESTADOS,
    ACOES_REQUISITO=ACOES,
    DECISOES_REQUISITO={
        "atende": "atende",
        "parcial": "atende em parte",
        "nao_sei": "não sei",
        "nao_atende": "não atende",
    },
)
_URL = re.compile(r"^(https?://)?[\w.-]+\.[a-z]{2,}(/\S*)?$", re.IGNORECASE)


def _linhas(texto: str) -> list[str]:
    """Um item por linha (ou separado por vírgula), sem repetidos nem vazios."""
    itens = (item.strip() for linha in texto.splitlines() for item in linha.split(","))
    return list(dict.fromkeys(item for item in itens if item))


def _tela_criterios(request: Request, perfil: Perfil, erro: str = "", salvo: bool = False):
    return templates.TemplateResponse(
        request,
        "criterios.html",
        {"perfil": perfil, "c": perfil.criterios, "erro": erro, "salvo": salvo},
        status_code=400 if erro else 200,
    )


@router.get("/p/{slug}/criterios", response_class=HTMLResponse)
def ver_criterios(request: Request, perfil: PerfilAtual, salvo: bool = False):
    return _tela_criterios(request, perfil, salvo=salvo)


@router.post("/p/{slug}/criterios", response_class=HTMLResponse)
def salvar_criterios(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    modalidades: Annotated[list[str] | None, Form()] = None,
    senioridades: Annotated[list[str] | None, Form()] = None,
    cidades: Annotated[str, Form()] = "",
    salario_minimo: Annotated[str, Form()] = "",
    empresas_evitar: Annotated[str, Form()] = "",
    palavras_evitar: Annotated[str, Form()] = "",
):
    try:
        minimo = ler_decimal(salario_minimo.replace(".", "")) if salario_minimo.strip() else None
        criterios = Criterios(
            modalidades=modalidades or [],
            senioridades=senioridades or [],
            cidades=_linhas(cidades),
            salario_minimo=minimo,
            empresas_evitar=_linhas(empresas_evitar),
            palavras_evitar=_linhas(palavras_evitar),
        )
    except ValueError as erro:
        detalhe = (
            "; ".join(descrever_erro(e) for e in erro.errors())
            if isinstance(erro, ValidationError)
            else str(erro)
        )
        return _tela_criterios(request, perfil, erro=detalhe)
    if not criterios.modalidades:
        return _tela_criterios(request, perfil, erro="Marque ao menos uma modalidade.")
    salvar_perfil(pasta, perfil.model_copy(update={"criterios": criterios}))
    return ir(f"/p/{perfil.slug}/criterios?salvo=1")


# --- avaliar uma vaga -----------------------------------------------------------


def _tela_vagas(request: Request, perfil: Perfil, erro: str = "", entrada: str = "", status=200):
    engine = banco_do_perfil(perfil.slug)
    concordancia = servico.concordancia(engine)
    return templates.TemplateResponse(
        request,
        "vagas.html",
        {
            "perfil": perfil,
            "vagas": servico.listar_vagas(engine),
            "lacunas": servico.lacunas_recorrentes(engine),
            "concordancia": concordancia,
            "acertos": sum(app == sua for _, app, sua in concordancia),
            "erro": erro,
            "entrada": entrada,
        },
        status_code=status,
    )


@router.get("/p/{slug}/vagas", response_class=HTMLResponse)
def ver_vagas(request: Request, perfil: PerfilAtual):
    return _tela_vagas(request, perfil)


@router.post("/p/{slug}/vagas", response_class=HTMLResponse)
def nova_vaga(request: Request, perfil: PerfilAtual, entrada: Annotated[str, Form()] = ""):
    """URL ou texto colado; a mesma vaga de novo abre a que já existe."""
    limpa = entrada.strip()
    try:
        bruta = ler_url(limpa) if _URL.match(limpa) else ler_texto(limpa)
    except ErroLeituraVaga as erro:
        return _tela_vagas(request, perfil, str(erro), entrada, 400)
    vaga, nova = servico.registrar_vaga(banco_do_perfil(perfil.slug), bruta)
    if nova:
        return ir(f"/p/{perfil.slug}/vagas/{vaga.id}/avaliar")
    return ir(f"/p/{perfil.slug}/vagas/{vaga.id}?repetida=1")


def _vaga(perfil: Perfil, vaga_id: int) -> Vaga:
    vaga = servico.obter_vaga(banco_do_perfil(perfil.slug), vaga_id)
    if vaga is None:
        raise HTTPException(404, "Vaga não encontrada.")
    return vaga


@router.get("/p/{slug}/vagas/{vaga_id}/avaliar", response_class=HTMLResponse)
async def avaliar_vaga(
    request: Request, pasta: Pasta, perfil: PerfilAtual, vaga_id: int, forcar: bool = False
):
    """GET de propósito: no modo manual, a resposta colada volta para cá e sai do cache."""
    vaga = _vaga(perfil, vaga_id)
    engine = banco_do_perfil(perfil.slug)
    try:
        doc = carregar_dossie(pasta, engine, perfil)
        await servico.avaliar(perfil, engine, vaga, doc, forcar=forcar)
    except ErroDossie as erro:
        mensagem = f"O dossiê tem um erro; corrija antes de avaliar. {erro}"
        return _tela_vaga(request, pasta, perfil, vaga, mensagem, 409)
    except ErroIA as erro:
        mensagem = f"A IA não conseguiu avaliar a vaga. {erro.mensagem}"
        return _tela_vaga(request, pasta, perfil, vaga, mensagem, 502)
    return ir(f"/p/{perfil.slug}/vagas/{vaga_id}")


def _tela_vaga(
    request: Request, pasta, perfil: Perfil, vaga: Vaga, erro: str = "", status=200, **extra
):
    engine = banco_do_perfil(perfil.slug)
    avaliacao = servico.ultima_avaliacao(engine, vaga.id)
    atuais, versao_atual = {}, None
    try:
        doc = carregar_dossie(pasta, engine, perfil)
        atuais = {f.id: f for f in doc.fatos}
        versao_atual = doc.metadados.get("versao")
    except ErroDossie:
        pass
    requisitos = servico.efetivos(engine, avaliacao) if avaliacao else []
    contam = [r for r in requisitos if r["aplica"]]
    contexto = {
        "perfil": perfil,
        "vaga": vaga,
        "meta": servico.metadados_da_vaga(vaga),
        "avaliacao": avaliacao,
        "filtros": json.loads(avaliacao.filtros) if avaliacao else None,
        "alertas": json.loads(avaliacao.alertas) if avaliacao else [],
        "forcas": [r for r in contam if r["decisao"] in ("atende", "parcial")],
        "lacunas": [r for r in contam if r["decisao"] in ("nao_atende", "nao_sei")],
        "fora": [r for r in requisitos if not r["aplica"]],
        "atuais": atuais,
        "dossie_mudou": bool(
            avaliacao and versao_atual and avaliacao.versao_dossie != versao_atual
        ),
        "chamada": servico.custo_da_avaliacao(engine, avaliacao) if avaliacao else None,
        "TIPOS": ROTULOS_TIPO,
        "TIPO_DA_CATEGORIA": servico.TIPO_DA_CATEGORIA,
        "erro": erro,
        **extra,
    }
    return templates.TemplateResponse(request, "vaga.html", contexto, status_code=status)


@router.get("/p/{slug}/vagas/{vaga_id}", response_class=HTMLResponse)
def ver_vaga(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    vaga_id: int,
    repetida: bool = False,
    adicionado: str = "",
):
    vaga = _vaga(perfil, vaga_id)
    return _tela_vaga(request, pasta, perfil, vaga, repetida=repetida, adicionado=adicionado)


@router.post("/p/{slug}/vagas/{vaga_id}/estado")
def mudar_estado(
    perfil: PerfilAtual,
    vaga_id: int,
    estado: Annotated[Literal["avaliada", "quero_aplicar", "descartada"], Form()],
):
    _vaga(perfil, vaga_id)
    servico.atualizar_vaga(banco_do_perfil(perfil.slug), vaga_id, estado=estado)
    return ir(f"/p/{perfil.slug}/vagas/{vaga_id}")


# --- feedback por requisito (decisão 0005: o que a pessoa afirma entra direto) ----------


def _avaliacao_atual(perfil: Perfil, vaga_id: int):
    _vaga(perfil, vaga_id)
    avaliacao = servico.ultima_avaliacao(banco_do_perfil(perfil.slug), vaga_id)
    if avaliacao is None or avaliacao.bloqueada:
        raise HTTPException(404, "Esta vaga ainda não tem avaliação.")
    return avaliacao


def _ir_requisito(perfil: Perfil, vaga_id: int, posicao: int, consulta: str = ""):
    return ir(f"/p/{perfil.slug}/vagas/{vaga_id}{consulta}#requisito-{posicao}")


@router.post("/p/{slug}/vagas/{vaga_id}/requisitos/{posicao}/tenho", response_class=HTMLResponse)
def tenho_isso(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    vaga_id: int,
    posicao: int,
    texto: Annotated[str, Form()],
    tipo: Annotated[str, Form()],
    empresa: Annotated[str, Form()] = "",
):
    avaliacao = _avaliacao_atual(perfil, vaga_id)
    engine = banco_do_perfil(perfil.slug)
    try:
        fato_id = servico.tenho_isso(
            pasta, engine, perfil, avaliacao.id, posicao, texto, tipo, empresa
        )
    except servico.ErroVaga as erro:
        vaga = _vaga(perfil, vaga_id)
        return _tela_vaga(request, pasta, perfil, vaga, f"Não deu para registrar: {erro}", 400)
    except ErroDossie as erro:
        vaga = _vaga(perfil, vaga_id)
        return _tela_vaga(request, pasta, perfil, vaga, f"O dossiê tem um erro. {erro}", 409)
    return _ir_requisito(perfil, vaga_id, posicao, f"?adicionado={fato_id}")


@router.post("/p/{slug}/vagas/{vaga_id}/requisitos/{posicao}/ajuste")
def ajustar(
    perfil: PerfilAtual,
    vaga_id: int,
    posicao: int,
    acao: Annotated[Literal["nao_tenho", "nao_se_aplica", "nao_e_bem_assim"], Form()],
):
    avaliacao = _avaliacao_atual(perfil, vaga_id)
    try:
        servico.ajustar(banco_do_perfil(perfil.slug), avaliacao.id, posicao, acao)
    except servico.ErroVaga as erro:
        raise HTTPException(404, str(erro)) from erro
    return _ir_requisito(perfil, vaga_id, posicao)


@router.post("/p/{slug}/vagas/{vaga_id}/requisitos/{posicao}/desfazer", response_class=HTMLResponse)
def desfazer(request: Request, pasta: Pasta, perfil: PerfilAtual, vaga_id: int, posicao: int):
    avaliacao = _avaliacao_atual(perfil, vaga_id)
    try:
        servico.desfazer(pasta, banco_do_perfil(perfil.slug), perfil, avaliacao.id, posicao)
    except ErroDossie as erro:
        vaga = _vaga(perfil, vaga_id)
        return _tela_vaga(request, pasta, perfil, vaga, f"O dossiê tem um erro. {erro}", 409)
    return _ir_requisito(perfil, vaga_id, posicao)


@router.post("/p/{slug}/vagas/{vaga_id}/faixa")
def marcar_faixa(
    perfil: PerfilAtual,
    vaga_id: int,
    faixa: Annotated[Literal["A", "B", "C", "D", ""], Form()] = "",
):
    """A faixa que a pessoa daria: mede a concordância com o app (critério de pronto)."""
    _vaga(perfil, vaga_id)
    servico.atualizar_vaga(banco_do_perfil(perfil.slug), vaga_id, faixa_esperada=faixa or None)
    return ir(f"/p/{perfil.slug}/vagas/{vaga_id}")
