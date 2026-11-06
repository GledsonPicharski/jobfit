"""CV por vaga: gerar, revisar o rascunho (com a checagem em código) e gerar o PDF."""

import json
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.cv import servico as cvs
from app.cv.checagem import frases
from app.cv.modelos import SECOES_DE_FRASES, Rascunho
from app.cv.tabelas import CV
from app.db import banco_do_perfil
from app.dossie.formato import ErroDossie
from app.dossie.versoes import carregar_dossie
from app.ia import ErroIA
from app.perfis.modelos import Perfil
from app.vagas import servico as vagas
from app.vagas.tabelas import Vaga
from app.web.rotas import Pasta, PerfilAtual, ir, templates
from app.web.rotas_vagas import _tela_vaga

router = APIRouter()

TITULOS_SECAO = {
    "pt": {
        "resumo": "Resumo",
        "experiencias": "Experiência",
        "competencias": "Competências",
        "formacao": "Formação",
        "idiomas": "Idiomas",
        "certificacoes": "Certificações",
        "outros": "Prêmios, publicações e docência",
    },
    "en": {
        "resumo": "Summary",
        "experiencias": "Experience",
        "competencias": "Skills",
        "formacao": "Education",
        "idiomas": "Languages",
        "certificacoes": "Certifications",
        "outros": "Awards, publications and teaching",
    },
}
templates.env.globals.update(TITULOS_SECAO_CV=TITULOS_SECAO, SECOES_DE_FRASES=SECOES_DE_FRASES)
_ACAO_CARGO = re.compile(r"^cargo_(dossie|confirmar):(\d+)$")


def _vaga(perfil: Perfil, vaga_id: int) -> Vaga:
    vaga = vagas.obter_vaga(banco_do_perfil(perfil.slug), vaga_id)
    if vaga is None:
        raise HTTPException(404, "Vaga não encontrada.")
    return vaga


def _cv(perfil: Perfil, cv_id: int) -> CV:
    cv = cvs.obter_cv(banco_do_perfil(perfil.slug), cv_id)
    if cv is None:
        raise HTTPException(404, "CV não encontrado.")
    return cv


@router.get("/p/{slug}/vagas/{vaga_id}/cv", response_class=HTMLResponse)
async def gerar_cv(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    vaga_id: int,
    idioma: Literal["pt", "en"] = "pt",
):
    """GET de propósito: no modo manual, a resposta colada volta para cá e sai do cache."""
    vaga = _vaga(perfil, vaga_id)
    engine = banco_do_perfil(perfil.slug)
    try:
        doc = carregar_dossie(pasta, engine, perfil)
        cv = await cvs.gerar(perfil, engine, doc, vaga, idioma)
    except (ErroDossie, cvs.ErroCV) as erro:
        return _erro_na_vaga(request, pasta, perfil, vaga, f"Não deu para montar o CV. {erro}")
    except ErroIA as erro:
        mensagem = f"A IA não conseguiu redigir o CV. {erro.mensagem}"
        return _erro_na_vaga(request, pasta, perfil, vaga, mensagem, 502)
    return ir(f"/p/{perfil.slug}/cvs/{cv.id}")


def _erro_na_vaga(request, pasta, perfil, vaga, mensagem, status=409):
    return _tela_vaga(request, pasta, perfil, vaga, mensagem, status)


def _cabecalho(perfil: Perfil, doc) -> list[str]:
    """Contato para o topo do CV: só o valor, sem o rótulo ("E-mail: x" → "x")."""
    contatos = cvs.selecionar_contato(doc)
    return [c.texto.split(":", 1)[1].strip() if ":" in c.texto else c.texto for c in contatos]


def _tela_cv(request: Request, pasta, perfil: Perfil, cv: CV, erro: str = "", status=200):
    engine = banco_do_perfil(perfil.slug)
    doc = carregar_dossie(pasta, engine, perfil)
    vaga = vagas.obter_vaga(engine, cv.vaga_id) if cv.vaga_id else None
    rascunho = cvs.rascunho_do_cv(cv)
    checagem = cvs.checar_cv(cv, doc, vaga)
    fatos = {f.id: f for f in doc.fatos}
    contexto = {
        "perfil": perfil,
        "cv": cv,
        "vaga": vaga,
        "r": rascunho,
        "problemas": checagem.problemas,
        "checagem": checagem,
        "fatos": fatos,
        "linhas_cargo": [
            cvs.linhas_do_cargo(fatos[e.cargo_id], cv.idioma) if e.cargo_id in fatos else (None, "")
            for e in rascunho.experiencias
        ],
        "originais": [
            (fatos[e.cargo_id].cargo or fatos[e.cargo_id].texto) if e.cargo_id in fatos else ""
            for e in rascunho.experiencias
        ],
        "cabecalho": _cabecalho(perfil, doc),
        "alertas": json.loads(cv.alertas),
        "chamada": cvs.custo(engine, cv),
        "titulos": TITULOS_SECAO[cv.idioma],
        "erro": erro,
    }
    return templates.TemplateResponse(request, "cv.html", contexto, status_code=status)


@router.get("/p/{slug}/cvs/{cv_id}", response_class=HTMLResponse)
def ver_cv(request: Request, pasta: Pasta, perfil: PerfilAtual, cv_id: int):
    try:
        return _tela_cv(request, pasta, perfil, _cv(perfil, cv_id))
    except ErroDossie as erro:
        raise HTTPException(409, f"O dossiê tem um erro. {erro}") from erro


def aplicar_formulario(rascunho: Rascunho, form) -> Rascunho:
    """Os textos editados e as frases a remover (ou apagadas) entram no rascunho."""
    novo = rascunho.model_copy(deep=True)
    remover = set(form.getlist("remover"))
    for caminho, frase in frases(novo):
        if caminho in form:
            frase.texto = str(form[caminho]).strip()
            if not frase.texto:
                remover.add(caminho)
    for i, exp in enumerate(novo.experiencias):
        if (campo := f"experiencias.{i}.titulo") in form and str(form[campo]).strip():
            exp.titulo = str(form[campo]).strip()
        exp.bullets = [
            b for j, b in enumerate(exp.bullets) if f"experiencias.{i}.bullets.{j}" not in remover
        ]
    for secao in SECOES_DE_FRASES:
        itens = getattr(novo, secao)
        setattr(novo, secao, [f for i, f in enumerate(itens) if f"{secao}.{i}" not in remover])
    return novo


@router.post("/p/{slug}/cvs/{cv_id}", response_class=HTMLResponse)
async def salvar_cv(request: Request, pasta: Pasta, perfil: PerfilAtual, cv_id: int):
    """Salva as edições; a ação do botão decide o que vem depois (cargo, PDF)."""
    cv = _cv(perfil, cv_id)
    engine = banco_do_perfil(perfil.slug)
    form = await request.form()
    rascunho = aplicar_formulario(cvs.rascunho_do_cv(cv), form)
    acao = str(form.get("acao", "salvar"))
    if m := _ACAO_CARGO.match(acao):
        i = int(m.group(2))
        if not 0 <= i < len(rascunho.experiencias):
            raise HTTPException(404, "Experiência não encontrada.")
        exp = rascunho.experiencias[i]
        doc = carregar_dossie(pasta, engine, perfil)
        try:
            cargo = doc.fato(exp.cargo_id)
        except KeyError as erro:
            raise HTTPException(404, "Cargo não encontrado no dossiê.") from erro
        if m.group(1) == "dossie":
            exp.titulo = cargo.cargo or cargo.texto
        elif rascunho.idioma == "en":
            cvs.confirmar_traducao(pasta, engine, perfil, exp.cargo_id, exp.titulo)
    cv = cvs.salvar_rascunho(engine, cv_id, rascunho)
    if acao == "pdf":
        return await _gerar_pdf(request, pasta, perfil, cv)
    return ir(f"/p/{perfil.slug}/cvs/{cv_id}")


async def _gerar_pdf(request: Request, pasta, perfil: Perfil, cv: CV):
    return _tela_cv(request, pasta, perfil, cv, "O PDF chega na próxima etapa.", 501)
