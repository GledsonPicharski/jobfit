"""Importar entradas para o dossiê e revisar as propostas (regra 4: nada sem aprovação)."""

import json
from pathlib import PurePath
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse

from app.db import banco_do_perfil
from app.dossie.formato import ErroDossie
from app.dossie.modelos import Periodo
from app.dossie.propostas import (
    ErroProposta,
    aplicar_importacao,
    atualizar_importacao,
    candidatos_propostos,
    criar_importacao,
    dados_efetivos,
    decidir,
    descartar_importacao,
    listar_importacoes,
    montar_propostas,
    obter_importacao,
    propostas_da_importacao,
    registrar_propostas,
    rejeitados_anteriores,
)
from app.dossie.tabelas import Importacao, Proposta
from app.dossie.versoes import carregar_dossie
from app.ia import ErroIA, executar
from app.ia.tarefas import EXTRAIR_FATOS, EntradaExtracao
from app.ingestao.arquivos import LIMITE_TEXTO, ErroArquivo, ler_enviado, salvar_fonte
from app.ingestao.extracao import candidatos_da_ia, mascarar
from app.ingestao.linkedin_pdf import FONTE as FONTE_LINKEDIN
from app.ingestao.linkedin_pdf import ErroLeitura, ler_linkedin_pdf, texto_das_descricoes
from app.ingestao.texto import LIMITE_CARACTERES, decodificar, secoes, texto_das_secoes
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
FONTE_TEXTO = "texto"
_FONTES = {FONTE_LINKEDIN: "PDF do LinkedIn", "cv": "CV", FONTE_TEXTO: "Texto"}
# Como a IA deve ler o texto de cada fonte (ver prompts/extrair_fatos).
_FONTE_PARA_IA = {FONTE_TEXTO: "texto", "cv": "cv", FONTE_LINKEDIN: "descricoes_linkedin"}
templates.env.globals.update(ACOES_PROPOSTA=_ACOES, DECISOES_PROPOSTA=_DECISOES)
templates.env.globals["FONTES_IMPORTACAO"] = _FONTES


def _url(perfil: Perfil, importacao_id: int, sufixo: str = "") -> str:
    return f"/p/{perfil.slug}/importacoes/{importacao_id}{sufixo}"


def _ler_fonte(pasta, perfil: Perfil, relativo: str) -> str:
    return decodificar((pasta_perfil(pasta, perfil.slug) / relativo).read_bytes())


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
    pasta_do_perfil = pasta_perfil(pasta, perfil.slug)
    relativo = salvar_fonte(pasta_do_perfil, nome, conteudo)
    importacao = criar_importacao(engine, FONTE_LINKEDIN, nome, relativo)
    montagem = montar_propostas(doc.fatos, lido.candidatos, rejeitados_anteriores(engine))
    registrar_propostas(engine, importacao.id, montagem)
    if lido.descricoes:  # resumo e descrições dos cargos: só a IA tira fatos delas
        texto = texto_das_descricoes(lido)
        descricoes = salvar_fonte(pasta_do_perfil, "descricoes.md", texto.encode("utf-8"))
        atualizar_importacao(engine, importacao.id, extraido=descricoes, extracao="pendente")
    return ir(_url(perfil, importacao.id))


def _texto_enviado(
    texto: str, nome: str, arquivo: UploadFile | None
) -> tuple[str, str, str, bytes]:
    """(texto, nome para a tela, nome do arquivo em fontes/, bytes a guardar)."""
    if arquivo is not None and arquivo.filename:
        conteudo = ler_enviado(arquivo.file)
        return decodificar(conteudo), arquivo.filename, arquivo.filename, conteudo
    texto = decodificar(texto.encode("utf-8"))  # o navegador manda CRLF
    if not texto.strip():
        raise ErroArquivo(400, "Cole um texto ou escolha um arquivo .md ou .txt.")
    nome = nome.strip() or "Texto colado"
    return texto, nome, f"{nome}.md", texto.encode("utf-8")


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _grande_demais(caracteres: int) -> str:
    return (
        f"O texto tem {_milhar(caracteres)} caracteres; o limite numa importação é "
        f"{_milhar(LIMITE_CARACTERES)}. Divida em partes ou use um .md com títulos e "
        "marque as seções."
    )


@router.post("/p/{slug}/importar/texto", response_class=HTMLResponse)
def importar_texto(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    texto: Annotated[str, Form()] = "",
    nome: Annotated[str, Form()] = "",
    arquivo: Annotated[UploadFile | None, File()] = None,
):
    engine = banco_do_perfil(perfil.slug)
    try:
        lido, nome_tela, nome_arquivo, conteudo = _texto_enviado(texto, nome, arquivo)
        carregar_dossie(pasta, engine, perfil)
    except ErroArquivo as erro:
        return _tela_importar(request, perfil, str(erro), erro.status)
    except ErroDossie as erro:
        mensagem = f"O dossiê tem um erro; corrija antes de importar. {erro}"
        return _tela_importar(request, perfil, mensagem, 409)

    com_titulos = sum(s.nivel > 0 for s in secoes(lido)) >= 2
    if not com_titulos and len(lido) > LIMITE_CARACTERES:
        return _tela_importar(request, perfil, _grande_demais(len(lido)), 413)

    relativo = salvar_fonte(pasta_perfil(pasta, perfil.slug), nome_arquivo, conteudo)
    if com_titulos:
        importacao = criar_importacao(engine, FONTE_TEXTO, nome_tela, relativo, status="secoes")
        return ir(_url(perfil, importacao.id, "/secoes"))
    importacao = criar_importacao(engine, FONTE_TEXTO, nome_tela, relativo)
    atualizar_importacao(engine, importacao.id, extraido=relativo, extracao="pendente")
    return ir(_url(perfil, importacao.id, "/extrair"))


# --- escolher seções e extrair com a IA -----------------------------------------


def _tela_secoes(
    request: Request, pasta, perfil: Perfil, importacao: Importacao, erro="", status=200
):
    texto = _ler_fonte(pasta, perfil, importacao.arquivo or "")
    contexto = {
        "perfil": perfil,
        "importacao": importacao,
        "secoes": secoes(texto),
        "limite": LIMITE_CARACTERES,
        "erro": erro,
    }
    return templates.TemplateResponse(request, "secoes.html", contexto, status_code=status)


@router.get("/p/{slug}/importacoes/{importacao_id}/secoes", response_class=HTMLResponse)
def ver_secoes(request: Request, pasta: Pasta, perfil: PerfilAtual, importacao_id: int):
    importacao = _importacao(perfil, importacao_id)
    if importacao.status != "secoes":
        return ir(_url(perfil, importacao_id))
    return _tela_secoes(request, pasta, perfil, importacao)


@router.post("/p/{slug}/importacoes/{importacao_id}/secoes", response_class=HTMLResponse)
def marcar_secoes(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    importacao_id: int,
    secao: Annotated[list[int] | None, Form()] = None,
):
    importacao = _importacao(perfil, importacao_id)
    if importacao.status != "secoes":
        return ir(_url(perfil, importacao_id))
    texto = texto_das_secoes(_ler_fonte(pasta, perfil, importacao.arquivo or ""), secao or [])
    if not texto.strip():
        return _tela_secoes(request, pasta, perfil, importacao, "Marque ao menos uma seção.", 400)
    if len(texto) > LIMITE_CARACTERES:
        erro = _grande_demais(len(texto))
        return _tela_secoes(request, pasta, perfil, importacao, erro, 413)

    nome = f"{PurePath(importacao.nome).stem}_secoes.md"
    relativo = salvar_fonte(pasta_perfil(pasta, perfil.slug), nome, texto.encode("utf-8"))
    engine = banco_do_perfil(perfil.slug)
    atualizar_importacao(
        engine, importacao_id, status="revisao", extraido=relativo, extracao="pendente"
    )
    return ir(_url(perfil, importacao_id, "/extrair"))


@router.get("/p/{slug}/importacoes/{importacao_id}/extrair", response_class=HTMLResponse)
async def extrair(request: Request, pasta: Pasta, perfil: PerfilAtual, importacao_id: int):
    """GET de propósito: no modo manual, a resposta colada volta para cá e sai do cache."""
    importacao = _importacao(perfil, importacao_id)
    pendente = importacao.status == "revisao" and importacao.extracao == "pendente"
    if not pendente or not importacao.extraido:
        return ir(_url(perfil, importacao_id))
    engine = banco_do_perfil(perfil.slug)
    try:
        doc = carregar_dossie(pasta, engine, perfil)
    except ErroDossie as erro:
        mensagem = f"O dossiê tem um erro; corrija antes de continuar. {erro}"
        return _tela_importacao(request, pasta, perfil, importacao, mensagem, 409)

    # E-mail, telefone e CPF saem antes; o texto vai como dado, num campo JSON.
    enviado, contatos = mascarar(_ler_fonte(pasta, perfil, importacao.extraido), importacao.fonte)
    entrada = EntradaExtracao(fonte=_FONTE_PARA_IA[importacao.fonte], texto=enviado)
    try:
        saida = await executar(perfil, EXTRAIR_FATOS, entrada, engine=engine)
    except ErroIA as erro:
        mensagem = f"A IA não conseguiu ler o texto. {erro.mensagem}"
        return _tela_importacao(request, pasta, perfil, importacao, mensagem, 502)

    candidatos = contatos + candidatos_da_ia(saida, enviado, importacao.fonte)
    montagem = montar_propostas(
        doc.fatos,
        candidatos,
        rejeitados_anteriores(engine),
        candidatos_propostos(engine, importacao),
    )
    registrar_propostas(engine, importacao_id, montagem, extracao_feita=True)
    return ir(_url(perfil, importacao_id))


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
    aberta = importacao.status == "revisao"
    return {
        "perfil": perfil,
        "importacao": importacao,
        "cartoes": [_cartao(p) for p in propostas],
        "pendentes": sum(p.decisao == "pendente" for p in propostas),
        "atuais": atuais,
        "aberta": aberta,
        "extracao_pendente": aberta and importacao.extracao == "pendente",
    }


def _tela_importacao(
    request: Request, pasta, perfil: Perfil, importacao: Importacao, erro="", status=200
):
    contexto = {**_contexto(pasta, perfil, importacao), "erro": erro}
    return templates.TemplateResponse(request, "importacao.html", contexto, status_code=status)


@router.get("/p/{slug}/importacoes/{importacao_id}", response_class=HTMLResponse)
def ver_importacao(request: Request, pasta: Pasta, perfil: PerfilAtual, importacao_id: int):
    importacao = _importacao(perfil, importacao_id)
    if importacao.status == "secoes":
        return ir(_url(perfil, importacao_id, "/secoes"))
    return _tela_importacao(request, pasta, perfil, importacao)


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
        return _tela_importacao(request, pasta, perfil, importacao, str(erro), 409)
    if versao is None:
        return ir(_url(perfil, importacao_id))
    return ir(f"/p/{perfil.slug}/dossie/historico/{versao.versao}")


@router.post("/p/{slug}/importacoes/{importacao_id}/descartar", response_class=HTMLResponse)
def descartar(request: Request, pasta: Pasta, perfil: PerfilAtual, importacao_id: int):
    importacao = _importacao(perfil, importacao_id)
    try:
        descartar_importacao(banco_do_perfil(perfil.slug), importacao_id)
    except ErroProposta as erro:
        return _tela_importacao(request, pasta, perfil, importacao, str(erro), 409)
    return ir(f"/p/{perfil.slug}/importar")
