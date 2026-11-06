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

from sqlalchemy import Engine

from app import config
from app.db import banco_do_perfil
from app.ia.erros import AguardandoResposta, PedidoIndisponivel, RespostaInvalida
from app.ia.manual import obter_pedido, pedidos_pendentes, responder_pedido
from app.ia.modelos import PedidoIA
from app.perfis.modelos import Perfil
from app.perfis.servico import ErroPerfil, carregar_perfil

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
