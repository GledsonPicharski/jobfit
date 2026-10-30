"""Importar entradas para o dossiê e revisar as propostas (regra 4: nada sem aprovação)."""

import json
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse

from app.db import banco_do_perfil
from app.dossie.formato import ErroDossie
from app.dossie.modelos import Periodo
from app.dossie.propostas import (
    ErroProposta,
    aplicar_importacao,
    criar_importacao,
    dados_efetivos,
    decidir,
    listar_importacoes,
    montar_propostas,
    obter_importacao,
    propostas_da_importacao,
    registrar_propostas,
    rejeitados_anteriores,
)
from app.dossie.tabelas import Importacao, Proposta
from app.dossie.versoes import carregar_dossie
from app.ingestao.arquivos import LIMITE_TEXTO, ErroArquivo, ler_enviado, salvar_fonte
from app.ingestao.linkedin_pdf import FONTE as FONTE_LINKEDIN
from app.ingestao.linkedin_pdf import ErroLeitura, ler_linkedin_pdf
from app.perfis.modelos import Perfil
from app.perfis.servico import pasta_perfil
from app.web.rotas import Pasta, PerfilAtual, ir, templates

router = APIRouter()

_ACOES = {"novo": "Novo", "alterar": "Completar período", "conflito": "Conflito"}
_DECISOES = {
    "pendente": "Pendente",
    "aprovada": "Aprovada",
    "editada": "Editada",
    "rejeitada": "Rejeitada",
}
_FONTES = {FONTE_LINKEDIN: "PDF do LinkedIn", "cv": "CV", "texto": "Texto"}
templates.env.globals.update(ACOES_PROPOSTA=_ACOES, DECISOES_PROPOSTA=_DECISOES)
templates.env.globals["FONTES_IMPORTACAO"] = _FONTES


# --- importar -------------------------------------------------------------------


def _tela_importar(request: Request, perfil: Perfil, erro: str = "", status: int = 200):
    importacoes = listar_importacoes(banco_do_perfil(perfil.slug))
    return templates.TemplateResponse(
        request,
        "importar.html",
        {"perfil": perfil, "importacoes": importacoes, "erro": erro, "limite": LIMITE_TEXTO},
        status_code=status,
    )


@router.get("/p/{slug}/importar", response_class=HTMLResponse)
def importar(request: Request, perfil: PerfilAtual):
    return _tela_importar(request, perfil)


@router.post("/p/{slug}/importar/linkedin", response_class=HTMLResponse)
def importar_linkedin(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    arquivo: Annotated[UploadFile, File()],
):
    engine = banco_do_perfil(perfil.slug)
    try:
        conteudo = ler_enviado(arquivo.file)
        lido = ler_linkedin_pdf(conteudo)
        doc = carregar_dossie(pasta, engine, perfil)
    except ErroArquivo as erro:
        return _tela_importar(request, perfil, str(erro), erro.status)
    except ErroLeitura as erro:
        return _tela_importar(request, perfil, str(erro), 400)
    except ErroDossie as erro:
        mensagem = f"O dossiê tem um erro; corrija antes de importar. {erro}"
        return _tela_importar(request, perfil, mensagem, 409)

    nome = arquivo.filename or "linkedin.pdf"
    relativo = salvar_fonte(pasta_perfil(pasta, perfil.slug), nome, conteudo)
    importacao = criar_importacao(engine, FONTE_LINKEDIN, nome, relativo)
    montagem = montar_propostas(doc.fatos, lido.candidatos, rejeitados_anteriores(engine))
    registrar_propostas(engine, importacao.id, montagem)
    return ir(f"/p/{perfil.slug}/importacoes/{importacao.id}")


# --- revisar --------------------------------------------------------------------


def _importacao(perfil: Perfil, importacao_id: int) -> Importacao:
    importacao = obter_importacao(banco_do_perfil(perfil.slug), importacao_id)
    if importacao is None:
        raise HTTPException(404, "Importação não encontrada.")
    return importacao


def _cartao(proposta: Proposta) -> dict:
    """O que a tela mostra de uma proposta: os dados efetivos, já decodificados."""
    dados = dados_efetivos(proposta)
    periodo = Periodo.model_validate(dados["periodo"]) if dados.get("periodo") else None
    return {
        "p": proposta,
        "dados": {**dados, "periodo": periodo},
        "alertas": json.loads(proposta.alertas),
    }


def _contexto(pasta, perfil: Perfil, importacao: Importacao) -> dict:
    engine = banco_do_perfil(perfil.slug)
    propostas = propostas_da_importacao(engine, importacao.id)
    atuais = {}
    try:
        doc = carregar_dossie(pasta, engine, perfil)
        atuais = {f.id: f for f in doc.fatos}
    except ErroDossie:
        pass  # a tela da importação ainda abre; gravar vai mostrar o erro
    return {
        "perfil": perfil,
        "importacao": importacao,
        "cartoes": [_cartao(p) for p in propostas],
        "pendentes": sum(p.decisao == "pendente" for p in propostas),
        "atuais": atuais,
        "aberta": importacao.status == "revisao",
    }


@router.get("/p/{slug}/importacoes/{importacao_id}", response_class=HTMLResponse)
def ver_importacao(request: Request, pasta: Pasta, perfil: PerfilAtual, importacao_id: int):
    importacao = _importacao(perfil, importacao_id)
    return templates.TemplateResponse(
        request, "importacao.html", _contexto(pasta, perfil, importacao)
    )


def _edicao(texto: str, empresa: str, cargo: str, inicio: str, fim: str) -> dict[str, object]:
    periodo = {"inicio": inicio.strip(), "fim": fim.strip() or None} if inicio.strip() else None
    return {
        "texto": texto.strip(),
        "empresa": empresa.strip() or None,
        "cargo": cargo.strip() or None,
        "periodo": periodo,
    }


@router.post(
    "/p/{slug}/importacoes/{importacao_id}/propostas/{proposta_id}", response_class=HTMLResponse
)
def decidir_proposta(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    importacao_id: int,
    proposta_id: int,
    decisao: Annotated[Literal["aprovada", "editada", "rejeitada", "pendente"], Form()],
    texto: Annotated[str, Form()] = "",
    empresa: Annotated[str, Form()] = "",
    cargo: Annotated[str, Form()] = "",
    inicio: Annotated[str, Form()] = "",
    fim: Annotated[str, Form()] = "",
):
    importacao = _importacao(perfil, importacao_id)
    engine = banco_do_perfil(perfil.slug)
    propostas = {p.id: p for p in propostas_da_importacao(engine, importacao_id)}
    if proposta_id not in propostas:
        raise HTTPException(404, "Proposta não encontrada nesta importação.")
    erro = ""
    edicao = _edicao(texto, empresa, cargo, inicio, fim) if decisao == "editada" else None
    try:
        decidir(engine, proposta_id, decisao, edicao)
    except ErroProposta as falha:
        erro = str(falha)
    if request.headers.get("HX-Request") != "true":
        if erro:
            raise HTTPException(409, erro)
        return ir(f"/p/{perfil.slug}/importacoes/{importacao_id}#proposta-{proposta_id}")

    contexto = _contexto(pasta, perfil, importacao)
    cartao = next(c for c in contexto["cartoes"] if c["p"].id == proposta_id)
    return templates.TemplateResponse(
        request,
        "_proposta.html",
        {**contexto, "c": cartao, "erro": erro, "oob": True},
    )


@router.post("/p/{slug}/importacoes/{importacao_id}/aprovar-pendentes")
def aprovar_pendentes(perfil: PerfilAtual, importacao_id: int):
    _importacao(perfil, importacao_id)
    engine = banco_do_perfil(perfil.slug)
    for proposta in propostas_da_importacao(engine, importacao_id):
        if proposta.decisao == "pendente":
            decidir(engine, proposta.id, "aprovada")
    return ir(f"/p/{perfil.slug}/importacoes/{importacao_id}")


@router.post("/p/{slug}/importacoes/{importacao_id}/gravar", response_class=HTMLResponse)
def gravar(request: Request, pasta: Pasta, perfil: PerfilAtual, importacao_id: int):
    importacao = _importacao(perfil, importacao_id)
    try:
        versao = aplicar_importacao(pasta, banco_do_perfil(perfil.slug), perfil, importacao_id)
    except (ErroProposta, ErroDossie) as erro:
        contexto = {**_contexto(pasta, perfil, importacao), "erro": str(erro)}
        return templates.TemplateResponse(request, "importacao.html", contexto, status_code=409)
    if versao is None:
        return ir(f"/p/{perfil.slug}/importacoes/{importacao_id}")
    return ir(f"/p/{perfil.slug}/dossie/historico/{versao.versao}")
