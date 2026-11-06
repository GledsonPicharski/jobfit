"""Ferramentas do JobFit para o Claude Desktop (decisão 0008).

O MCP é mais um caminho de resposta para os pedidos do modo manual: a ferramenta roda o
mesmo serviço da tela; se ele levantar `AguardandoResposta`, o pacote do pedido vai para
o Claude, que responde por `responder_pedido`. A resposta passa pela mesma validação e vai
para o cache; a ferramenta chamada de novo a encontra lá. Nada aqui grava no dossiê.

Cada função devolve o texto que o Claude lê; erro para o Claude é `ErroFerramenta`.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import anyio
from sqlalchemy import Engine

from app import config
from app.cv import servico as cvs
from app.cv.checagem import frases
from app.db import banco_do_perfil
from app.dossie.formato import Documento, ErroDossie
from app.dossie.versoes import carregar_dossie
from app.ia.erros import AguardandoResposta, ErroIA, PedidoIndisponivel, RespostaInvalida
from app.ia.manual import obter_pedido, pedidos_pendentes, responder_pedido
from app.ia.modelos import PedidoIA
from app.perfis.modelos import Perfil
from app.perfis.servico import ErroPerfil, carregar_perfil
from app.vagas import servico as vagas
from app.vagas.leitura import ErroLeituraVaga, ler_entrada
from app.vagas.tabelas import Avaliacao, Vaga

ORIGEM = "claude_desktop"


class ErroFerramenta(Exception):
    """Mensagem para o Claude, em português; vira um resultado de erro da ferramenta."""


@dataclass
class Contexto:
    """O perfil é relido a cada chamada: o que mudar na tela vale na hora."""

    slug: str | None = None

    def pasta(self) -> Path:
        pasta = config.carregar_config().pasta_dados
        if pasta is None:
            raise ErroFerramenta("O JobFit ainda não foi configurado. Abra o app (uv run jobfit).")
        return pasta

    def perfil(self) -> Perfil:
        slug = self.slug or config.carregar_config().ultimo_perfil
        if not slug:
            raise ErroFerramenta("Nenhum perfil no JobFit ainda. Crie um no app.")
        try:
            return carregar_perfil(self.pasta(), slug)
        except ErroPerfil as erro:
            raise ErroFerramenta(f"Perfil {slug!r} não encontrado no JobFit.") from erro

    def engine(self) -> Engine:
        return banco_do_perfil(self.perfil().slug)

    def dossie(self, perfil: Perfil, engine: Engine) -> Documento:
        try:
            return carregar_dossie(self.pasta(), engine, perfil)
        except ErroDossie as erro:
            raise ErroFerramenta(f"O dossiê tem um erro; corrija no app antes. {erro}") from erro

    def link(self, caminho: str) -> str:
        return f"http://127.0.0.1:{config.carregar_config().porta}{caminho}"


def texto_do_pedido(pedido: PedidoIA, depois: str) -> str:
    """O pacote do modo manual, com o jeito de responder trocado pela ferramenta."""
    return (
        f"O JobFit precisa que você faça a tarefa do pedido {pedido.id}, descrita abaixo.\n"
        f"Não escreva o JSON no chat: chame a ferramenta `responder_pedido` com "
        f'pedido_id="{pedido.id}" e, em `resposta`, só o objeto que segue o JSON Schema do '
        f'fim do pedido (sem o envelope com "pedido"). {depois}\n\n'
        f"---\n\n{pedido.pacote}"
    )


def aguardando(erro: AguardandoResposta, depois: str) -> str:
    return texto_do_pedido(erro.pedido, depois)


def listar_pedidos(ctx: Contexto) -> str:
    pendentes = pedidos_pendentes(ctx.engine())
    if not pendentes:
        return "Nenhum pedido do JobFit esperando resposta."
    linhas = [f"- {p.id}: {p.tarefa} v{p.versao_prompt}" for p in pendentes]
    return "Pedidos esperando resposta (abra cada um com `ver_pedido`):\n" + "\n".join(linhas)


def ver_pedido(ctx: Contexto, pedido_id: str) -> str:
    pedido = obter_pedido(ctx.engine(), pedido_id.strip().upper())
    if pedido is None:
        raise ErroFerramenta(f"Não existe o pedido {pedido_id} neste perfil.")
    if pedido.status != "pendente":
        return f"O pedido {pedido.id} não está mais esperando resposta ({pedido.status})."
    return texto_do_pedido(
        pedido, "Se o pedido veio da tela do JobFit, ela segue sozinha depois da resposta."
    )


def _texto_da_resposta(pedido_id: str, resposta: dict | str) -> str:
    """Aceita o objeto, o objeto em texto JSON ou o envelope completo do modo manual."""
    if isinstance(resposta, str):
        try:
            resposta = json.loads(resposta)
        except json.JSONDecodeError:
            return resposta  # a leitura do modo manual explica o que está quebrado
    if isinstance(resposta, dict) and "pedido" in resposta:
        return json.dumps(resposta, ensure_ascii=False)
    return json.dumps({"pedido": pedido_id, "resposta": resposta}, ensure_ascii=False)


def responder(ctx: Contexto, pedido_id: str, resposta: dict | str) -> str:
    pedido_id = pedido_id.strip().upper()
    texto = _texto_da_resposta(pedido_id, resposta)
    try:
        responder_pedido(ctx.engine(), pedido_id, texto, origem=ORIGEM)
    except RespostaInvalida as erro:
        raise ErroFerramenta(
            f"{erro.mensagem}\nCorrija e chame `responder_pedido` de novo, com o mesmo "
            f"pedido_id, mandando em `resposta` só o objeto do JSON Schema."
        ) from erro
    except PedidoIndisponivel as erro:
        raise ErroFerramenta(erro.mensagem) from erro
    return (
        f"Resposta do pedido {pedido_id} aceita e conferida pelo JobFit. Agora faça o passo "
        "indicado no pedido (em geral, chamar de novo a mesma ferramenta) para ver o "
        "resultado; se o pedido veio da tela do JobFit, ela segue sozinha."
    )


# --- vagas ------------------------------------------------------------------------


def _aviso_de_custo(perfil: Perfil) -> str:
    if not perfil.ia.precisa_chave:
        return ""
    return (
        f"\n(Este perfil está no modo API ({perfil.ia.provedor}): a IA foi chamada pela API, "
        "com o custo dela. Para usar a assinatura do Claude, troque para o modo manual em "
        "Configurar IA.)"
    )


def _linha_requisito(r: dict) -> str:
    peso = "obrigatório" if r["peso"] == "obrigatorio" else "desejável"
    linha = f"- {r['texto']} ({peso})"
    if r.get("justificativa"):
        linha += f": {r['justificativa']}"
    return linha


def resumo_da_avaliacao(ctx: Contexto, engine: Engine, vaga: Vaga, avaliacao: Avaliacao) -> str:
    titulo = vaga.titulo or "Vaga sem título"
    partes = [f"Vaga {vaga.id}: {titulo}" + (f" · {vaga.empresa}" if vaga.empresa else "")]
    filtros = json.loads(avaliacao.filtros)
    if avaliacao.bloqueada:
        partes.append("Barrada pelos critérios da pessoa, sem chamar a IA:")
        partes += [f"- {b}" for b in filtros.get("bloqueios", [])]
        partes.append("Para avaliar mesmo assim, chame avaliar_vaga com forcar=true.")
    elif avaliacao.faixa:
        nome = vagas.FAIXAS[avaliacao.faixa]
        conclusao = (
            "vale a candidatura"
            if avaliacao.recomenda
            else "abaixo do corte; o JobFit não recomenda, mas a decisão é da pessoa"
        )
        partes.append(
            f"Nota do JobFit (calculada em código): {avaliacao.faixa} · {nome} · "
            f"{avaliacao.nota}/100: {conclusao}."
        )
        requisitos = [r for r in vagas.efetivos(engine, avaliacao) if r["aplica"]]
        forcas = [r for r in requisitos if r["decisao"] in ("atende", "parcial")]
        lacunas = [r for r in requisitos if r["decisao"] in ("nao_atende", "nao_sei")]
        if forcas:
            partes += ["", "Forças:", *(_linha_requisito(r) for r in forcas)]
        if lacunas:
            partes += ["", "Lacunas:", *(_linha_requisito(r) for r in lacunas)]
    else:
        partes.append("A IA não achou requisitos nesta vaga; confira a descrição no app.")
    partes += [f"⚠ {a}" for a in filtros.get("alertas", [])]
    partes += [
        "",
        f"No app (para ajustar requisitos, dizer 'eu tenho isso' ou gerar o CV): "
        f"{ctx.link(f'/p/{ctx.perfil().slug}/vagas/{vaga.id}')}",
    ]
    return "\n".join(partes)


async def avaliar_vaga(
    ctx: Contexto, vaga: str | None = None, vaga_id: int | None = None, forcar: bool = False
) -> str:
    perfil = ctx.perfil()
    engine = banco_do_perfil(perfil.slug)
    if vaga_id is not None:
        registrada = vagas.obter_vaga(engine, vaga_id)
        if registrada is None:
            raise ErroFerramenta(f"Não existe a vaga {vaga_id} neste perfil (veja listar_vagas).")
    elif vaga and vaga.strip():
        try:
            bruta = await anyio.to_thread.run_sync(ler_entrada, vaga)
        except ErroLeituraVaga as erro:
            raise ErroFerramenta(str(erro)) from erro
        registrada, _ = vagas.registrar_vaga(engine, bruta)
    else:
        raise ErroFerramenta("Mande a URL ou o texto da vaga em `vaga`, ou o `vaga_id`.")

    doc = ctx.dossie(perfil, engine)
    try:
        avaliacao = await vagas.avaliar(perfil, engine, registrada, doc, forcar=forcar)
    except AguardandoResposta as erro:
        forcado = ", forcar=true" if forcar else ""
        return aguardando(
            erro, f"Depois, chame avaliar_vaga(vaga_id={registrada.id}{forcado}) para ver a nota."
        )
    except ErroIA as erro:
        raise ErroFerramenta(f"A IA não conseguiu avaliar a vaga. {erro.mensagem}") from erro
    return resumo_da_avaliacao(ctx, engine, registrada, avaliacao) + _aviso_de_custo(perfil)


def listar(ctx: Contexto, limite: int = 20) -> str:
    lista = vagas.listar_vagas(ctx.engine())[:limite]
    if not lista:
        return "Nenhuma vaga no JobFit ainda. Mande uma URL ou um texto para avaliar_vaga."
    linhas = []
    for vaga, avaliacao in lista:
        nota = (
            f"{avaliacao.faixa} ({vagas.FAIXAS[avaliacao.faixa]}, {avaliacao.nota}/100)"
            if avaliacao and avaliacao.faixa
            else "barrada pelos critérios"
            if avaliacao and avaliacao.bloqueada
            else "sem nota"
        )
        estado = vagas.ESTADOS.get(vaga.estado, vaga.estado).lower()
        empresa = f" · {vaga.empresa}" if vaga.empresa else ""
        linhas.append(
            f"- vaga_id={vaga.id}: {vaga.titulo or 'sem título'}{empresa} · {nota} · {estado}"
        )
    return "Vagas mais recentes:\n" + "\n".join(linhas)


# --- CV ---------------------------------------------------------------------------

IDIOMAS = {"pt": "português", "en": "inglês"}


def resumo_do_cv(ctx: Contexto, cv, checagem) -> str:
    """O que o Claude mostra à pessoa: o rascunho e o que a checagem achou, sem o contato."""
    rascunho = cvs.rascunho_do_cv(cv)
    textos = {caminho: frase.texto for caminho, frase in frases(rascunho)}
    for i, exp in enumerate(rascunho.experiencias):
        textos[f"experiencias.{i}.titulo"] = f"cargo {exp.titulo}"
    partes = [
        f"Rascunho do CV em {IDIOMAS[cv.idioma]} (cv_id={cv.id}) para a vaga {cv.vaga_id}.",
        f"Título: {rascunho.titulo.texto}",
        *(f"Resumo: {f.texto}" for f in rascunho.resumo),
    ]
    for exp in rascunho.experiencias:
        partes.append(f"{exp.titulo}:")
        partes += [f"  - {b.texto}" for b in exp.bullets]
    if checagem.bloqueios:
        partes += [
            "",
            f"A checagem do JobFit bloqueia o PDF por {checagem.bloqueios} problema(s): "
            "frases com número, ano, empresa ou cargo sem fato de origem no dossiê.",
        ]
    else:
        partes += ["", "A checagem do JobFit não achou bloqueios: o PDF pode ser gerado no app."]
    for caminho, problemas in checagem.problemas.items():
        for p in problemas:
            rotulo = "bloqueia" if p.nivel == "bloqueio" else "alerta"
            partes.append(f"- ({rotulo}) {textos.get(caminho, caminho)}: {p.mensagem}")
    partes += [
        "",
        "A pessoa revisa, edita e gera o PDF no app (o JobFit não gera o PDF por aqui): "
        f"{ctx.link(f'/p/{ctx.perfil().slug}/cvs/{cv.id}')}",
    ]
    return "\n".join(partes)


async def gerar_cv(
    ctx: Contexto, vaga_id: int, idioma: str | None = None, novo: bool = False
) -> str:
    perfil = ctx.perfil()
    engine = banco_do_perfil(perfil.slug)
    vaga = vagas.obter_vaga(engine, vaga_id)
    if vaga is None:
        raise ErroFerramenta(f"Não existe a vaga {vaga_id} neste perfil (veja listar_vagas).")
    idioma = idioma or ("en" if vaga.idioma == "en" else "pt")
    if idioma not in IDIOMAS:
        raise ErroFerramenta('O idioma do CV é "pt" ou "en".')
    doc = ctx.dossie(perfil, engine)
    try:
        cv = await cvs.gerar(perfil, engine, doc, vaga, idioma, novo=novo)
    except AguardandoResposta as erro:
        novo_arg = ", novo=true" if novo else ""
        return aguardando(
            erro,
            f'Depois, chame gerar_cv(vaga_id={vaga.id}, idioma="{idioma}"{novo_arg}) para ver '
            "o rascunho e a checagem.",
        )
    except cvs.ErroCV as erro:
        raise ErroFerramenta(f"Não deu para montar o CV. {erro}") from erro
    except ErroIA as erro:
        raise ErroFerramenta(f"A IA não conseguiu redigir o CV. {erro.mensagem}") from erro
    return resumo_do_cv(ctx, cv, cvs.checar_cv(cv, doc, vaga)) + _aviso_de_custo(perfil)
