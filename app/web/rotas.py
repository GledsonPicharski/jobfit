"""Telas da Fase 0: pasta de dados, perfis, configuração de IA e teste de conexão.

Toda tela de perfil fica sob `/p/{slug}/`, para nenhuma misturar dados de dois perfis.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app import config
from app.db import banco_do_perfil
from app.ia import ErroIA, executar_detalhado
from app.ia.chaves import salvar_chave, tem_chave
from app.ia.custos import gasto_do_dia, gasto_do_mes, para_micro_usd
from app.ia.modelos import ChamadaIA
from app.ia.tarefas import TESTAR_CONEXAO
from app.perfis.modelos import MODELOS_PADRAO, PROVEDORES, Perfil, Provedor
from app.perfis.servico import (
    ErroPerfil,
    carregar_perfil,
    criar_perfil,
    listar_perfis,
    salvar_perfil,
)
from app.web.formatos import formatar_hora_local, formatar_usd, ler_decimal

PASTA_TEMPLATES = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=PASTA_TEMPLATES)
templates.env.filters["usd"] = formatar_usd
templates.env.filters["hora"] = formatar_hora_local
templates.env.globals["PROVEDORES"] = PROVEDORES

router = APIRouter()


class PastaNaoConfigurada(Exception):
    pass


def exigir_pasta() -> Path:
    pasta = config.carregar_config().pasta_dados
    if pasta is None:
        raise PastaNaoConfigurada
    return pasta


def obter_perfil(slug: str, pasta: Annotated[Path, Depends(exigir_pasta)]) -> Perfil:
    try:
        return carregar_perfil(pasta, slug)
    except ErroPerfil as erro:
        raise HTTPException(404, "Perfil não encontrado.") from erro


Pasta = Annotated[Path, Depends(exigir_pasta)]
PerfilAtual = Annotated[Perfil, Depends(obter_perfil)]


def _ir(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _lembrar_perfil(slug: str) -> None:
    cfg = config.carregar_config()
    if cfg.ultimo_perfil != slug:
        config.salvar_config(cfg.model_copy(update={"ultimo_perfil": slug}))


@router.get("/", response_class=HTMLResponse)
def inicio(request: Request, pasta: Pasta):
    return templates.TemplateResponse(
        request, "inicio.html", {"perfis": listar_perfis(pasta), "pasta": pasta}
    )


@router.get("/configurar-pasta", response_class=HTMLResponse)
def configurar_pasta(request: Request):
    atual = config.carregar_config().pasta_dados
    sugestao = atual or Path.home() / "Documents" / "JobFit"
    return templates.TemplateResponse(request, "configurar_pasta.html", {"valor": str(sugestao)})


@router.post("/configurar-pasta", response_class=HTMLResponse)
def salvar_pasta(request: Request, pasta: Annotated[str, Form()]):
    try:
        caminho = config.validar_pasta_dados(pasta)
    except config.ErroConfig as erro:
        return templates.TemplateResponse(
            request,
            "configurar_pasta.html",
            {"valor": pasta, "erro": str(erro)},
            status_code=400,
        )
    cfg = config.carregar_config()
    config.salvar_config(cfg.model_copy(update={"pasta_dados": caminho}))
    return _ir("/")


@router.get("/perfis/novo", response_class=HTMLResponse)
def novo_perfil(request: Request, _pasta: Pasta):
    return templates.TemplateResponse(request, "perfil_novo.html", {})


@router.post("/perfis", response_class=HTMLResponse)
def criar(
    request: Request,
    pasta: Pasta,
    nome: Annotated[str, Form()],
    slug: Annotated[str, Form()] = "",
):
    try:
        perfil = criar_perfil(pasta, nome, slug.strip() or None)
    except ErroPerfil as erro:
        return templates.TemplateResponse(
            request,
            "perfil_novo.html",
            {"nome": nome, "slug": slug, "erro": str(erro)},
            status_code=400,
        )
    _lembrar_perfil(perfil.slug)
    return _ir(f"/p/{perfil.slug}/ia")


@router.get("/p/{slug}", response_class=HTMLResponse)
def painel(request: Request, perfil: PerfilAtual):
    _lembrar_perfil(perfil.slug)
    engine = banco_do_perfil(perfil.slug)
    with Session(engine) as sessao:
        recentes = sessao.exec(select(ChamadaIA).order_by(ChamadaIA.id.desc()).limit(10)).all()
    return templates.TemplateResponse(
        request,
        "painel.html",
        {
            "perfil": perfil,
            "gasto_dia": gasto_do_dia(engine),
            "gasto_mes": gasto_do_mes(engine),
            "teto_micro": para_micro_usd(perfil.ia.teto_diario_usd),
            "tem_chave": tem_chave(perfil.slug, perfil.ia.provedor),
            "recentes": recentes,
        },
    )


def _tela_ia(request: Request, perfil: Perfil, **extra) -> HTMLResponse:
    contexto = {
        "perfil": perfil,
        "chaves": {p: tem_chave(perfil.slug, p) for p in PROVEDORES},
        "padroes": MODELOS_PADRAO[perfil.ia.provedor],
        **extra,
    }
    return templates.TemplateResponse(
        request, "perfil_ia.html", contexto, status_code=400 if "erro" in extra else 200
    )


@router.get("/p/{slug}/ia", response_class=HTMLResponse)
def configurar_ia(request: Request, perfil: PerfilAtual, salvo: bool = False):
    return _tela_ia(request, perfil, salvo=salvo)


@router.post("/p/{slug}/ia", response_class=HTMLResponse)
def salvar_ia(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    provedor: Annotated[Provedor, Form()],
    teto: Annotated[str, Form()],
    modelo_barato: Annotated[str, Form()] = "",
    modelo_forte: Annotated[str, Form()] = "",
    chave: Annotated[str, Form()] = "",
):
    try:
        teto_usd = ler_decimal(teto)
        if teto_usd < 0:
            raise ValueError("O teto não pode ser negativo.")
    except ValueError as erro:
        return _tela_ia(request, perfil, erro=f"Teto diário: {erro}")

    padroes = MODELOS_PADRAO[perfil.ia.provedor]
    ia = perfil.ia.model_copy(
        update={
            "teto_diario_usd": teto_usd,
            "modelos": {
                "barato": modelo_barato.strip() or padroes["barato"],
                "forte": modelo_forte.strip() or padroes["forte"],
            },
        }
    )
    if provedor != perfil.ia.provedor:
        ia = ia.com_provedor(provedor)
    salvar_perfil(pasta, perfil.model_copy(update={"ia": ia}))
    if chave.strip():
        salvar_chave(perfil.slug, provedor, chave)
    return _ir(f"/p/{perfil.slug}/ia?salvo=1")


@router.post("/p/{slug}/ia/testar", response_class=HTMLResponse)
async def testar_conexao(request: Request, perfil: PerfilAtual):
    try:
        resultado = await executar_detalhado(
            perfil, TESTAR_CONEXAO, "ping", engine=banco_do_perfil(perfil.slug), usar_cache=False
        )
    except ErroIA as erro:
        return templates.TemplateResponse(request, "_resultado_teste.html", {"erro": erro.mensagem})
    return templates.TemplateResponse(
        request,
        "_resultado_teste.html",
        {"saida": resultado.saida, "chamada": resultado.chamada},
    )
