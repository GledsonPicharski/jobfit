"""Vagas: critérios (filtros duros), avaliação, forças e lacunas."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from app.perfis.modelos import Criterios, Perfil
from app.perfis.servico import salvar_perfil
from app.vagas.metadados import MODALIDADES, SENIORIDADES
from app.validacao import descrever_erro
from app.web.formatos import ler_decimal
from app.web.rotas import Pasta, PerfilAtual, ir, templates

router = APIRouter()
templates.env.globals.update(MODALIDADES=MODALIDADES, SENIORIDADES=SENIORIDADES)


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
