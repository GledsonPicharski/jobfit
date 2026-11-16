"""Buscas salvas e o scan de portais (decisão 0009): nada aqui chama a IA."""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.db import banco_do_perfil
from app.perfis.modelos import Perfil
from app.vagas import scanner
from app.vagas.buscas import (
    ErroBusca,
    FiltrosBusca,
    excluir_busca,
    filtros_de,
    listar_buscas,
    obter_busca,
    salvar_busca,
)
from app.vagas.catalogo import carregar_catalogo
from app.web.rotas import Pasta, PerfilAtual, ir, templates
from app.web.rotas_vagas import _linhas

router = APIRouter()


def _nomes_dos_portais(pasta) -> dict[str, str]:
    return {p.id: p.nome for p in carregar_catalogo(pasta).portais} | {"colada": "colada por você"}


templates.env.globals.update(resumo_por_portal=scanner.resumo_por_portal)


def _tela_buscas(request: Request, pasta, perfil: Perfil, aviso: str = "", status: int = 200):
    engine = banco_do_perfil(perfil.slug)
    buscas = listar_buscas(engine)
    return templates.TemplateResponse(
        request,
        "buscas.html",
        {
            "perfil": perfil,
            "buscas": [(b, filtros_de(b)) for b in buscas],
            "varredura": scanner.ultima_varredura(engine),
            "rodando": scanner.em_andamento(engine),
            "nomes": _nomes_dos_portais(pasta),
            "aviso": aviso,
        },
        status_code=status,
    )


@router.get("/p/{slug}/buscas", response_class=HTMLResponse)
def ver_buscas(request: Request, pasta: Pasta, perfil: PerfilAtual):
    return _tela_buscas(request, pasta, perfil)


def _tela_busca(request: Request, pasta, perfil: Perfil, busca=None, erro="", form=None):
    ativos = carregar_catalogo(pasta).ativos()
    return templates.TemplateResponse(
        request,
        "busca.html",
        {
            "perfil": perfil,
            "busca": busca,
            "f": form or (filtros_de(busca) if busca else None),
            "ativa": busca.ativa if busca else True,
            "nome": busca.nome if busca else "",
            "portais": ativos,
            "erro": erro,
        },
        status_code=400 if erro else 200,
    )


@router.get("/p/{slug}/buscas/nova", response_class=HTMLResponse)
def nova_busca(request: Request, pasta: Pasta, perfil: PerfilAtual):
    return _tela_busca(request, pasta, perfil)


@router.get("/p/{slug}/buscas/{busca_id}", response_class=HTMLResponse)
def ver_busca(request: Request, pasta: Pasta, perfil: PerfilAtual, busca_id: int):
    busca = obter_busca(banco_do_perfil(perfil.slug), busca_id)
    if busca is None:
        raise HTTPException(404, "Busca não encontrada.")
    return _tela_busca(request, pasta, perfil, busca)


@router.post("/p/{slug}/buscas", response_class=HTMLResponse)
@router.post("/p/{slug}/buscas/{busca_id}", response_class=HTMLResponse)
def gravar_busca(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    nome: Annotated[str, Form()],
    titulos: Annotated[str, Form()] = "",
    paises: Annotated[str, Form()] = "",
    salario_minimo: Annotated[str, Form()] = "",
    empresas_excluidas: Annotated[str, Form()] = "",
    setores_excluidos: Annotated[str, Form()] = "",
    palavras_obrigatorias: Annotated[str, Form()] = "",
    palavras_proibidas: Annotated[str, Form()] = "",
    senioridades: Annotated[list[str] | None, Form()] = None,
    portais: Annotated[list[str] | None, Form()] = None,
    so_remoto: Annotated[bool, Form()] = False,
    ativa: Annotated[bool, Form()] = False,
    busca_id: int | None = None,
):
    engine = banco_do_perfil(perfil.slug)
    campos = {
        "titulos": [t.strip() for t in titulos.splitlines() if t.strip()],  # títulos têm vírgula
        "paises": _linhas(paises),
        "senioridades": senioridades or [],
        "empresas_excluidas": _linhas(empresas_excluidas),
        "setores_excluidos": _linhas(setores_excluidos),
        "palavras_obrigatorias": _linhas(palavras_obrigatorias),
        "palavras_proibidas": _linhas(palavras_proibidas),
        "portais": portais or [],
        "so_remoto": so_remoto,
        "ativa": ativa,
    }
    digitos = "".join(c for c in salario_minimo if c.isdigit())
    campos["salario_minimo"] = int(digitos) if digitos else None
    try:
        busca = salvar_busca(engine, nome=nome, busca_id=busca_id, **campos)
    except ErroBusca as erro:
        anterior = obter_busca(engine, busca_id) if busca_id else None
        listas = {k: v for k, v in campos.items() if k not in ("ativa",)}
        return _tela_busca(request, pasta, perfil, anterior, str(erro), FiltrosBusca(**listas))
    return ir(f"/p/{perfil.slug}/buscas?salva={busca.id}")


@router.post("/p/{slug}/buscas/{busca_id}/excluir")
def apagar_busca(perfil: PerfilAtual, busca_id: int):
    excluir_busca(banco_do_perfil(perfil.slug), busca_id)
    return ir(f"/p/{perfil.slug}/buscas")


# --- o scan ---------------------------------------------------------------------


@router.post("/p/{slug}/scan", response_class=HTMLResponse)
def rodar_scan(request: Request, pasta: Pasta, perfil: PerfilAtual):
    engine = banco_do_perfil(perfil.slug)
    if not listar_buscas(engine, so_ativas=True):
        aviso = "Crie uma busca (e deixe-a ativa) antes de rodar o scan."
        return _tela_buscas(request, pasta, perfil, aviso, 400)
    scanner.iniciar(perfil, engine, pasta)
    return ir(f"/p/{perfil.slug}/buscas")


@router.get("/p/{slug}/scan/estado", response_class=HTMLResponse)
def estado_do_scan(request: Request, pasta: Pasta, perfil: PerfilAtual):
    """Pedaço da tela que a página confere a cada poucos segundos enquanto o scan roda."""
    engine = banco_do_perfil(perfil.slug)
    return templates.TemplateResponse(
        request,
        "_varredura.html",
        {
            "perfil": perfil,
            "varredura": scanner.ultima_varredura(engine),
            "rodando": scanner.em_andamento(engine),
            "nomes": _nomes_dos_portais(pasta),
        },
    )
