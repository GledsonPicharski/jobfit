"""Buscas salvas e o scan de portais (decisão 0009): nada aqui chama a IA."""

from typing import Annotated
from urllib.parse import quote

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
from app.vagas.catalogo import (
    CATEGORIAS,
    MODOS,
    ErroCatalogo,
    acrescentar_empresa,
    acrescentar_portal,
    carregar_catalogo,
)
from app.vagas.leitura import novo_cliente
from app.vagas.metricas import (
    definir_lembrete,
    lembretes_vencidos,
    marcar_checado,
    metricas_por_portal,
)
from app.vagas.portais import ErroPortal, conferir_quadro, ler_quadro
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


# --- portais --------------------------------------------------------------------


def _tela_portais(request: Request, pasta, perfil: Perfil, aviso="", erro="", status=200):
    engine = banco_do_perfil(perfil.slug)
    catalogo = carregar_catalogo(pasta)
    registros = scanner.portais_do_perfil(engine)
    metricas = {m.portal: m for m in metricas_por_portal(engine)}  # já em ordem de resultado
    ordem = {portal: i for i, portal in enumerate(metricas)}
    ativos = sorted(catalogo.ativos(), key=lambda p: ordem.get(p.id, len(ordem)))
    lembretes = {}
    for portal in catalogo.lembretes():
        lembretes.setdefault(portal.categoria, []).append(portal)
    return templates.TemplateResponse(
        request,
        "portais.html",
        {
            "perfil": perfil,
            "ativos": ativos,
            "metricas": metricas,
            "registros": registros,
            "lembretes": lembretes,
            "vencidos": {p.id for p, _ in lembretes_vencidos(engine, catalogo)},
            "outros": [p for p in catalogo.portais if p.status != "ativo"],
            "empresas": catalogo.empresas,
            "nomes": {p.id: p.nome for p in catalogo.portais},
            "CATEGORIAS": CATEGORIAS,
            "MODOS": MODOS,
            "aviso": aviso,
            "erro": erro,
        },
        status_code=status,
    )


@router.get("/p/{slug}/portais", response_class=HTMLResponse)
def ver_portais(request: Request, pasta: Pasta, perfil: PerfilAtual, aviso: str = ""):
    return _tela_portais(request, pasta, perfil, aviso=aviso)


@router.post("/p/{slug}/portais/empresas", response_class=HTMLResponse)
def acrescentar_empresa_ats(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    nome: Annotated[str, Form()],
    quadro: Annotated[str, Form()],
    ats: Annotated[str, Form()] = "",
):
    """Confere o quadro ao vivo antes de salvar: uma empresa errada não entra no scan."""
    achado, identificador = ler_quadro(quadro)
    ats = achado or ats
    if ats not in ("greenhouse", "lever", "ashby"):
        erro = "Escolha o sistema da empresa (Greenhouse, Lever ou Ashby) ou cole o link do quadro."
        return _tela_portais(request, pasta, perfil, erro=erro, status=400)
    try:
        with novo_cliente() as cliente:
            vagas = conferir_quadro(ats, identificador, cliente)
        acrescentar_empresa(pasta, nome=nome, ats=ats, quadro=identificador)
    except (ErroPortal, ErroCatalogo) as erro:
        return _tela_portais(request, pasta, perfil, erro=f"Não acrescentei: {erro}.", status=400)
    aviso = f"{nome.strip()} acrescentada: o quadro tem {vagas} vaga(s) agora."
    return ir(f"/p/{perfil.slug}/portais?aviso={quote(aviso)}")


@router.post("/p/{slug}/portais/novo", response_class=HTMLResponse)
def acrescentar_portal_lembrete(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    nome: Annotated[str, Form()],
    url: Annotated[str, Form()] = "",
    categoria: Annotated[str, Form()] = "vagas",
    frequencia_dias: Annotated[int | None, Form()] = 7,
):
    try:
        portal = acrescentar_portal(
            pasta, nome=nome, url=url, categoria=categoria, frequencia_dias=frequencia_dias
        )
    except ErroCatalogo as erro:
        return _tela_portais(request, pasta, perfil, erro=str(erro), status=400)
    aviso = (
        f"{portal.nome} acrescentado: o JobFit lembra de checar a cada {frequencia_dias} dia(s)."
    )
    return ir(f"/p/{perfil.slug}/portais?aviso={quote(aviso)}")


@router.post("/p/{slug}/portais/{portal}/ligar")
def ligar(perfil: PerfilAtual, portal: str, ligado: Annotated[bool, Form()] = False):
    scanner.ligar_portal(banco_do_perfil(perfil.slug), portal, ligado)
    return ir(f"/p/{perfil.slug}/portais#lidos")


@router.post("/p/{slug}/portais/{portal}/lembrete")
def lembrete(
    perfil: PerfilAtual,
    portal: str,
    frequencia_dias: Annotated[str, Form()] = "",
    cadastro: Annotated[str, Form()] = "",
    observacoes: Annotated[str, Form()] = "",
):
    dias = int(frequencia_dias) if frequencia_dias.strip().isdigit() else None
    definir_lembrete(
        banco_do_perfil(perfil.slug),
        portal,
        frequencia_dias=dias,
        cadastro=cadastro or None,
        observacoes=observacoes,
    )
    return ir(f"/p/{perfil.slug}/portais#portal-{portal}")


@router.post("/p/{slug}/portais/{portal}/checado")
def checado(
    perfil: PerfilAtual,
    portal: str,
    observacoes: Annotated[str, Form()] = "",
    voltar: Annotated[str, Form()] = "",
):
    marcar_checado(banco_do_perfil(perfil.slug), portal, observacoes)
    if voltar == "inicio":
        return ir(f"/p/{perfil.slug}")
    return ir(f"/p/{perfil.slug}/portais#portal-{portal}")


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
