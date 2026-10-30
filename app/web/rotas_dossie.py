"""Telas do dossiê: fatos por seção, 🔒 e "não enviar à IA", Visão de CV e histórico."""

import json
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.arquivos import ler_texto
from app.db import banco_do_perfil
from app.dossie.estrutura import secoes_para_tela
from app.dossie.filtros import fatos_publicaveis
from app.dossie.formato import Documento, ErroDossie
from app.dossie.modelos import ROTULOS_TIPO, Fato
from app.dossie.propostas import importacoes_em_revisao
from app.dossie.versoes import (
    alterar_dossie,
    caminho_dossie,
    caminho_historico,
    carregar_dossie,
    diff_texto,
    obter_versao,
    versoes,
)
from app.perfis.modelos import Perfil
from app.web.formatos import formatar_periodo
from app.web.rotas import Pasta, PerfilAtual, ir, templates

templates.env.filters["periodo"] = formatar_periodo
templates.env.globals["ROTULOS_TIPO"] = ROTULOS_TIPO
templates.env.globals["MOTIVOS_VERSAO"] = {
    "criacao": "criação",
    "edicao_manual": "edição manual",
    "edicao_app": "edição no app",
    "importacao": "importação",
}

router = APIRouter()


def _tela_quebrada(request: Request, pasta, perfil: Perfil, erro: ErroDossie, status: int = 200):
    return templates.TemplateResponse(
        request,
        "dossie.html",
        {"perfil": perfil, "erro": erro, "arquivo": caminho_dossie(pasta, perfil.slug)},
        status_code=status,
    )


@router.get("/p/{slug}/dossie", response_class=HTMLResponse)
def ver_dossie(request: Request, pasta: Pasta, perfil: PerfilAtual, visao: str = ""):
    engine = banco_do_perfil(perfil.slug)
    try:
        doc = carregar_dossie(pasta, engine, perfil)
    except ErroDossie as erro:
        return _tela_quebrada(request, pasta, perfil, erro)
    secoes = secoes_para_tela(doc)
    if visao == "cv":
        publicaveis = {f.id for f in fatos_publicaveis(doc.fatos)}
        for secao in secoes:
            secao.fatos = [f for f in secao.fatos if f.id in publicaveis]
    return templates.TemplateResponse(
        request,
        "dossie.html",
        {
            "perfil": perfil,
            "doc": doc,
            "secoes": secoes,
            "visao": visao,
            "arquivo": caminho_dossie(pasta, perfil.slug),
            "importacoes": importacoes_em_revisao(engine),
            "propostos": [f for f in doc.fatos if f.status == "proposto"],
        },
    )


def _mudar_fato(
    request: Request, pasta, perfil: Perfil, fato_id: str, mudanca: Callable[[Fato], dict]
):
    """Uma edição no app: muda um fato e grava uma versão nova."""

    def trocar(doc: Documento) -> None:
        try:
            fato = doc.fato(fato_id)
        except KeyError as erro:
            raise HTTPException(404, "Fato não encontrado.") from erro
        doc.substituir_fato(fato.model_copy(update=mudanca(fato)))

    try:
        alterar_dossie(pasta, banco_do_perfil(perfil.slug), perfil, "edicao_app", trocar)
    except ErroDossie as erro:
        return _tela_quebrada(request, pasta, perfil, erro, status=409)
    return ir(f"/p/{perfil.slug}/dossie#{fato_id}")


@router.post("/p/{slug}/dossie/fatos/{fato_id}/alternar", response_class=HTMLResponse)
def alternar(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    fato_id: str,
    campo: Annotated[Literal["privado", "nao_enviar_ia"], Form()],
):
    return _mudar_fato(
        request, pasta, perfil, fato_id, lambda fato: {campo: not getattr(fato, campo)}
    )


@router.post("/p/{slug}/dossie/fatos/{fato_id}/status", response_class=HTMLResponse)
def decidir_status(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    fato_id: str,
    status: Annotated[Literal["confirmado", "rejeitado"], Form()],
):
    """Confirma ou rejeita um fato `proposto` escrito à mão (regra 4)."""
    return _mudar_fato(request, pasta, perfil, fato_id, lambda _: {"status": status})


@router.get("/p/{slug}/dossie/historico", response_class=HTMLResponse)
def historico(request: Request, perfil: PerfilAtual):
    lista = versoes(banco_do_perfil(perfil.slug))
    resumos = {v.versao: json.loads(v.resumo) for v in lista}
    return templates.TemplateResponse(
        request, "dossie_historico.html", {"perfil": perfil, "versoes": lista, "resumos": resumos}
    )


def _texto_da_versao(pasta, slug: str, versao: int | None) -> str:
    if versao is None:
        return ""
    try:
        return ler_texto(caminho_historico(pasta, slug, versao))
    except OSError:
        return ""


@router.get("/p/{slug}/dossie/historico/{numero}", response_class=HTMLResponse)
def ver_versao(request: Request, pasta: Pasta, perfil: PerfilAtual, numero: int):
    engine = banco_do_perfil(perfil.slug)
    versao = obter_versao(engine, numero)
    if versao is None:
        raise HTTPException(404, "Versão não encontrada.")
    anterior = next((v.versao for v in versoes(engine) if v.versao < numero), None)
    linhas = diff_texto(
        _texto_da_versao(pasta, perfil.slug, anterior),
        _texto_da_versao(pasta, perfil.slug, numero),
    )
    return templates.TemplateResponse(
        request,
        "dossie_versao.html",
        {
            "perfil": perfil,
            "versao": versao,
            "anterior": anterior,
            "resumo": json.loads(versao.resumo),
            "linhas": linhas,
        },
    )
