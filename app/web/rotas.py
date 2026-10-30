"""Telas da Fase 0: pasta de dados, perfis, configuração de IA, teste e pedidos do modo manual.

Toda tela de perfil fica sob `/p/{slug}/`, para nenhuma misturar dados de dois perfis.
"""

import contextlib
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app import config
from app.db import banco_do_perfil
from app.ia import (
    AguardandoResposta,
    ErroIA,
    PedidoIndisponivel,
    RespostaInvalida,
    executar_detalhado,
)
from app.ia.chaves import salvar_chave, tem_chave
from app.ia.custos import gasto_do_dia, gasto_do_mes, para_micro_usd
from app.ia.manual import cancelar_pedido, obter_pedido, pedidos_pendentes, responder_pedido
from app.ia.modelos import ChamadaIA, PedidoIA
from app.ia.tarefas import TESTAR_CONEXAO
from app.perfis.exclusao import excluir_perfil
from app.perfis.modelos import MODELOS_PADRAO, PROVEDORES, PROVEDORES_COM_CHAVE, Perfil, Provedor
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
templates.env.globals["PROVEDORES_COM_CHAVE"] = PROVEDORES_COM_CHAVE

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


def ir(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _lembrar_perfil(slug: str) -> None:
    cfg = config.carregar_config()
    if cfg.ultimo_perfil != slug:
        config.salvar_config(cfg.model_copy(update={"ultimo_perfil": slug}))


@router.get("/", response_class=HTMLResponse)
def inicio(request: Request, pasta: Pasta, excluido: str = ""):
    return templates.TemplateResponse(
        request,
        "inicio.html",
        {"perfis": listar_perfis(pasta), "pasta": pasta, "excluido": excluido},
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
    return ir("/")


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
    return ir(f"/p/{perfil.slug}/ia")


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
            "falta_chave": perfil.ia.precisa_chave
            and not tem_chave(perfil.slug, perfil.ia.provedor),
            "pendentes": pedidos_pendentes(engine),
            "recentes": recentes,
        },
    )


def _tela_ia(request: Request, perfil: Perfil, **extra) -> HTMLResponse:
    contexto = {
        "perfil": perfil,
        "chaves": {p: tem_chave(perfil.slug, p) for p in PROVEDORES_COM_CHAVE},
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
    if chave.strip() and provedor in PROVEDORES_COM_CHAVE:
        salvar_chave(perfil.slug, provedor, chave)
    return ir(f"/p/{perfil.slug}/ia?salvo=1")


@router.post("/p/{slug}/ia/testar", response_class=HTMLResponse)
async def testar_conexao(request: Request, perfil: PerfilAtual):
    engine = banco_do_perfil(perfil.slug)
    try:
        resultado = await executar_detalhado(
            perfil, TESTAR_CONEXAO, "ping", engine=engine, usar_cache=False
        )
    except AguardandoResposta as aguardando:
        # Modo manual: o resultado do teste aparece na própria tela do pedido, sem "voltar".
        return ir(f"/p/{perfil.slug}/pedidos/{aguardando.pedido.id}")
    except ErroIA as erro:
        return templates.TemplateResponse(request, "_resultado_teste.html", {"erro": erro.mensagem})
    return templates.TemplateResponse(
        request,
        "_resultado_teste.html",
        {"saida": resultado.saida, "chamada": resultado.chamada},
    )


@router.get("/p/{slug}/excluir", response_class=HTMLResponse)
def confirmar_exclusao(request: Request, pasta: Pasta, perfil: PerfilAtual):
    return templates.TemplateResponse(
        request, "perfil_excluir.html", {"perfil": perfil, "lixeira": pasta / "lixeira"}
    )


@router.post("/p/{slug}/excluir", response_class=HTMLResponse)
def excluir(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    confirmacao: Annotated[str, Form()] = "",
):
    contexto = {"perfil": perfil, "lixeira": pasta / "lixeira"}
    if confirmacao.strip() != perfil.slug:
        erro = f"Digite {perfil.slug} para confirmar."
        return templates.TemplateResponse(
            request, "perfil_excluir.html", {**contexto, "erro": erro}, status_code=400
        )
    try:
        excluir_perfil(pasta, perfil.slug)
    except ErroPerfil as erro:
        return templates.TemplateResponse(
            request, "perfil_excluir.html", {**contexto, "erro": str(erro)}, status_code=400
        )
    return ir(f"/?{urlencode({'excluido': perfil.nome})}")


# --- pedidos do modo manual ---------------------------------------------------


def voltar_seguro(slug: str, voltar: str) -> str | None:
    """Só caminhos do próprio perfil: evita redirecionar para fora do app."""
    partes = urlsplit(voltar)
    if partes.scheme or partes.netloc or "\\" in voltar:
        return None
    if partes.path != f"/p/{slug}" and not partes.path.startswith(f"/p/{slug}/"):
        return None
    return voltar


def _obter_pedido(perfil: Perfil, pedido_id: str) -> PedidoIA:
    pedido = obter_pedido(banco_do_perfil(perfil.slug), pedido_id)
    if pedido is None:
        raise HTTPException(404, "Pedido não encontrado.")
    return pedido


def _tela_pedido(
    request: Request, perfil: Perfil, pedido: PedidoIA, status_code: int = 200, **extra
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "pedido.html",
        {"perfil": perfil, "pedido": pedido, **extra},
        status_code=status_code,
    )


@router.get("/p/{slug}/pedidos/{pedido_id}", response_class=HTMLResponse)
def ver_pedido(request: Request, perfil: PerfilAtual, pedido_id: str, voltar: str = ""):
    pedido = _obter_pedido(perfil, pedido_id)
    return _tela_pedido(request, perfil, pedido, voltar=voltar_seguro(perfil.slug, voltar) or "")


@router.get("/p/{slug}/pedidos/{pedido_id}/pacote.md")
def baixar_pacote(perfil: PerfilAtual, pedido_id: str):
    pedido = _obter_pedido(perfil, pedido_id)
    return Response(
        pedido.pacote.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="jobfit-{pedido.id}.md"'},
    )


@router.post("/p/{slug}/pedidos/{pedido_id}/resposta", response_class=HTMLResponse)
def responder(
    request: Request,
    perfil: PerfilAtual,
    pedido_id: str,
    resposta: Annotated[str, Form()],
    voltar: Annotated[str, Form()] = "",
):
    engine = banco_do_perfil(perfil.slug)
    pedido = _obter_pedido(perfil, pedido_id)
    destino = voltar_seguro(perfil.slug, voltar)
    try:
        resultado = responder_pedido(engine, pedido.id, resposta)
    except RespostaInvalida as erro:
        return _tela_pedido(
            request,
            perfil,
            _obter_pedido(perfil, pedido_id),
            400,
            erro=erro.mensagem,
            correcao=erro.correcao,
            resposta=resposta,
            voltar=destino or "",
        )
    except PedidoIndisponivel as erro:
        return _tela_pedido(request, perfil, pedido, 400, erro=erro.mensagem)
    if destino:
        return ir(destino)
    return _tela_pedido(
        request,
        perfil,
        _obter_pedido(perfil, pedido_id),
        saida=resultado.saida,
        chamada=resultado.chamada,
    )


@router.post("/p/{slug}/pedidos/{pedido_id}/cancelar")
def cancelar(perfil: PerfilAtual, pedido_id: str):
    pedido = _obter_pedido(perfil, pedido_id)
    with contextlib.suppress(PedidoIndisponivel):  # já respondido ou cancelado: nada a fazer
        cancelar_pedido(banco_do_perfil(perfil.slug), pedido.id)
    return ir(f"/p/{perfil.slug}")
