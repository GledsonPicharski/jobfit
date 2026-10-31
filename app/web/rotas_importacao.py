"""Importar entradas para o dossiê e revisar as propostas (regra 4: nada sem aprovação)."""

import json
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse

from app.db import banco_do_perfil
from app.dossie.formato import Documento, ErroDossie, ler_dossie
from app.dossie.modelos import ROTULOS_TIPO, Fato, Periodo
from app.dossie.propostas import (
    CAMPOS_DO_FATO,
    Candidato,
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
from app.dossie.versoes import adotar_dossie, carregar_dossie
from app.ia import ErroIA, executar
from app.ia.tarefas import EXTRAIR_FATOS, EntradaExtracao
from app.ingestao.arquivos import LIMITE_TEXTO, ErroArquivo, ler_enviado, salvar_fonte
from app.ingestao.cv import FONTE as FONTE_CV
from app.ingestao.cv import ErroCV, texto_do_cv
from app.ingestao.extracao import candidatos_da_ia, mascarar
from app.ingestao.linkedin_pdf import FONTE as FONTE_LINKEDIN
from app.ingestao.linkedin_pdf import ErroLeitura, ler_linkedin_pdf, texto_das_descricoes
from app.ingestao.texto import LIMITE_CARACTERES, decodificar, secoes, texto_das_secoes
from app.perfis.modelos import Perfil
from app.perfis.servico import pasta_perfil
from app.web.rotas import Pasta, PerfilAtual, ir, templates

router = APIRouter()

FONTE_TEXTO = "texto"
_FONTES = {FONTE_LINKEDIN: "PDF do LinkedIn", FONTE_CV: "CV", FONTE_TEXTO: "Texto"}
# Como a IA deve ler o texto de cada fonte (ver prompts/extrair_fatos).
_FONTE_PARA_IA = {FONTE_TEXTO: "texto", FONTE_CV: "cv", FONTE_LINKEDIN: "descricoes_linkedin"}
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


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _grande_demais(caracteres: int) -> str:
    return (
        f"O texto tem {_milhar(caracteres)} caracteres; o limite numa importação é "
        f"{_milhar(LIMITE_CARACTERES)}. Divida em partes ou use um .md com títulos e "
        "marque as seções."
    )


def _importar_linkedin(pasta, perfil: Perfil, doc: Documento, nome: str, conteudo: bytes, lido):
    engine = banco_do_perfil(perfil.slug)
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


def _importar_cv(pasta, perfil: Perfil, nome: str, conteudo: bytes, texto: str):
    if len(texto) > LIMITE_CARACTERES:
        raise ErroArquivo(413, _grande_demais(len(texto)))
    engine = banco_do_perfil(perfil.slug)
    pasta_do_perfil = pasta_perfil(pasta, perfil.slug)
    relativo = salvar_fonte(pasta_do_perfil, nome, conteudo)
    extraido = salvar_fonte(pasta_do_perfil, f"{PurePath(nome).stem}.txt", texto.encode("utf-8"))
    importacao = criar_importacao(engine, FONTE_CV, nome, relativo)
    atualizar_importacao(engine, importacao.id, extraido=extraido, extracao="pendente")
    return ir(_url(perfil, importacao.id, "/extrair"))


def _candidato_do_fato(fato: Fato) -> Candidato:
    return Candidato.model_validate(
        {**fato.model_dump(include=set(CAMPOS_DO_FATO)), "fonte": FONTE_TEXTO}
    )


def _importar_texto(
    pasta, perfil: Perfil, doc: Documento, nome: str, arquivo: str, conteudo: bytes, texto: str
):
    engine = banco_do_perfil(perfil.slug)
    try:
        enviado = ler_dossie(texto)
    except ErroDossie as erro:
        raise ErroArquivo(400, f"O dossiê enviado tem um erro. {erro}") from erro
    if enviado.fatos and not doc.fatos:
        # Um dossiê pronto, num perfil ainda vazio: enviar já é aprovar.
        versao = adotar_dossie(pasta, engine, perfil, texto)
        return ir(f"/p/{perfil.slug}/dossie?gravado={versao.versao}")

    relativo = salvar_fonte(pasta_perfil(pasta, perfil.slug), arquivo, conteudo)
    if enviado.fatos:  # outro dossiê do JobFit: compara fato a fato, sem IA
        importacao = criar_importacao(engine, FONTE_TEXTO, nome, relativo)
        candidatos = [_candidato_do_fato(f) for f in enviado.fatos if f.status != "rejeitado"]
        montagem = montar_propostas(doc.fatos, candidatos, rejeitados_anteriores(engine))
        registrar_propostas(engine, importacao.id, montagem)
        return ir(_url(perfil, importacao.id))

    if sum(s.nivel > 0 for s in secoes(texto)) >= 2:
        importacao = criar_importacao(engine, FONTE_TEXTO, nome, relativo, status="secoes")
        return ir(_url(perfil, importacao.id, "/secoes"))
    if len(texto) > LIMITE_CARACTERES:
        raise ErroArquivo(413, _grande_demais(len(texto)))
    importacao = criar_importacao(engine, FONTE_TEXTO, nome, relativo)
    atualizar_importacao(engine, importacao.id, extraido=relativo, extracao="pendente")
    return ir(_url(perfil, importacao.id, "/extrair"))


def _dossie_para_importar(pasta, perfil: Perfil) -> Documento:
    try:
        return carregar_dossie(pasta, banco_do_perfil(perfil.slug), perfil)
    except ErroDossie as erro:
        raise ErroArquivo(409, f"O dossiê tem um erro; corrija antes de importar. {erro}") from erro


@router.post("/p/{slug}/importar/arquivo", response_class=HTMLResponse)
def importar_arquivo(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    arquivo: Annotated[UploadFile, File()],
):
    """Qualquer arquivo: o tipo sai do conteúdo (PDF do LinkedIn, CV, dossiê, texto)."""
    nome = arquivo.filename or "arquivo"
    try:
        conteudo = ler_enviado(arquivo.file)
        doc = _dossie_para_importar(pasta, perfil)
        if conteudo.startswith(b"%PDF"):
            try:
                lido = ler_linkedin_pdf(conteudo)
            except ErroLeitura:
                return _importar_cv(pasta, perfil, nome, conteudo, texto_do_cv(conteudo))
            return _importar_linkedin(pasta, perfil, doc, nome, conteudo, lido)
        if conteudo.startswith((b"PK\x03\x04", b"\xd0\xcf\x11\xe0")):
            return _importar_cv(pasta, perfil, nome, conteudo, texto_do_cv(conteudo))
        if b"\x00" in conteudo[:4096]:
            raise ErroArquivo(400, "Não reconheci o arquivo. Envie PDF, DOCX, .md ou .txt.")
        texto = decodificar(conteudo)
        return _importar_texto(pasta, perfil, doc, nome, nome, conteudo, texto)
    except ErroArquivo as erro:
        return _tela_importar(request, perfil, str(erro), erro.status)
    except ErroCV as erro:
        return _tela_importar(request, perfil, str(erro), 400)


@router.post("/p/{slug}/importar/texto", response_class=HTMLResponse)
def importar_texto(
    request: Request,
    pasta: Pasta,
    perfil: PerfilAtual,
    texto: Annotated[str, Form()] = "",
    nome: Annotated[str, Form()] = "",
):
    texto = decodificar(texto.encode("utf-8"))  # o navegador manda CRLF
    nome = nome.strip() or "Texto colado"
    try:
        if not texto.strip():
            raise ErroArquivo(400, "Cole um texto antes de continuar.")
        doc = _dossie_para_importar(pasta, perfil)
        conteudo = texto.encode("utf-8")
        return _importar_texto(pasta, perfil, doc, nome, f"{nome}.md", conteudo, texto)
    except ErroArquivo as erro:
        return _tela_importar(request, perfil, str(erro), erro.status)


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


def _usar_fonte(proposta: Proposta) -> bool:
    """Num conflito, o que está marcado: a decisão já tomada ou a sugestão."""
    if proposta.decisao != "pendente":
        return proposta.decisao in ("aprovada", "editada")
    return proposta.sugestao in ("usar_nova", "aprovar")


def _contexto(pasta, perfil: Perfil, importacao: Importacao) -> dict:
    engine = banco_do_perfil(perfil.slug)
    cartoes = [_cartao(p) for p in propostas_da_importacao(engine, importacao.id)]
    atuais = {}
    try:
        doc = carregar_dossie(pasta, engine, perfil)
        atuais = {f.id: f for f in doc.fatos}
    except ErroDossie:
        pass  # a tela da importação ainda abre; aplicar vai mostrar o erro
    novos = [c for c in cartoes if c["p"].acao == "novo"]
    grupos: dict[str, list[dict]] = {}
    for tipo in ROTULOS_TIPO:  # na ordem dos tipos, não na da fonte
        if itens := [c for c in novos if c["dados"]["tipo"] == tipo]:
            grupos[tipo] = itens
    aberta = importacao.status == "revisao"
    return {
        "perfil": perfil,
        "importacao": importacao,
        "cartoes": cartoes,
        "conflitos": [c for c in cartoes if c["p"].acao != "novo"],
        "grupos": grupos,
        "usar_fonte": {c["p"].id: _usar_fonte(c["p"]) for c in cartoes},
        "atuais": atuais,
        "inicial": not atuais,
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


def _edicao(form, proposta: Proposta) -> dict[str, object] | None:
    """Os campos editados de um item, ou None se a pessoa não mudou nada."""
    if f"texto-{proposta.id}" not in form:
        return None

    def campo(nome: str) -> str:
        return str(form.get(f"{nome}-{proposta.id}", "")).strip()

    inicio, fim = campo("inicio"), campo("fim")
    edicao = {
        "texto": campo("texto"),
        "empresa": campo("empresa") or None,
        "cargo": campo("cargo") or None,
        "periodo": {"inicio": inicio, "fim": fim or None} if inicio else None,
    }
    original = json.loads(proposta.dados)
    if all(original.get(k) == v for k, v in edicao.items()):
        return None
    return edicao


@router.post("/p/{slug}/importacoes/{importacao_id}/aplicar", response_class=HTMLResponse)
async def aplicar(request: Request, pasta: Pasta, perfil: PerfilAtual, importacao_id: int):
    """Uma decisão para o lote: o marcado entra, o desmarcado não volta a ser proposto."""
    importacao = _importacao(perfil, importacao_id)
    if importacao.status != "revisao":
        return ir(_url(perfil, importacao_id))
    form = await request.form()
    aceitas = set(form.getlist("aceitas"))
    engine = banco_do_perfil(perfil.slug)
    try:
        for proposta in propostas_da_importacao(engine, importacao_id):
            if proposta.acao != "novo":
                escolha = form.get(f"conflito-{proposta.id}")
                usar = escolha == "fonte" if escolha else _usar_fonte(proposta)
                decidir(engine, proposta.id, "aprovada" if usar else "rejeitada")
            elif str(proposta.id) not in aceitas:
                decidir(engine, proposta.id, "rejeitada")
            elif (edicao := _edicao(form, proposta)) is not None:
                decidir(engine, proposta.id, "editada", edicao)
            else:
                decidir(engine, proposta.id, "aprovada")
        versao = aplicar_importacao(pasta, engine, perfil, importacao_id)
    except (ErroProposta, ErroDossie) as erro:
        return _tela_importacao(request, pasta, perfil, importacao, str(erro), 400)
    if versao is None:
        return ir(_url(perfil, importacao_id))
    return ir(f"/p/{perfil.slug}/dossie?gravado={versao.versao}")


@router.post("/p/{slug}/importacoes/{importacao_id}/descartar", response_class=HTMLResponse)
def descartar(request: Request, pasta: Pasta, perfil: PerfilAtual, importacao_id: int):
    importacao = _importacao(perfil, importacao_id)
    try:
        descartar_importacao(banco_do_perfil(perfil.slug), importacao_id)
    except ErroProposta as erro:
        return _tela_importacao(request, pasta, perfil, importacao, str(erro), 409)
    return ir(f"/p/{perfil.slug}/importar")
