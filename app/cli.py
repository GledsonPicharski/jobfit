"""Linha de comando. `jobfit` sobe o app em 127.0.0.1 e abre o navegador."""

import socket
import threading
import time
import webbrowser
from typing import Annotated

import typer
import uvicorn

from app.config import carregar_config

HOST = "127.0.0.1"  # nunca 0.0.0.0: o app não pode ficar visível na rede

cli = typer.Typer(add_completion=False, help="JobFit: app local de evolução de carreira.")


def porta_em_uso(porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conexao:
        conexao.settimeout(0.5)
        return conexao.connect_ex((HOST, porta)) == 0


def configurar_servidor(porta: int) -> uvicorn.Config:
    return uvicorn.Config("app.main:create_app", factory=True, host=HOST, port=porta)


def _abrir_quando_pronto(servidor: uvicorn.Server, url: str) -> None:
    for _ in range(300):
        if servidor.started:
            webbrowser.open(url)
            return
        time.sleep(0.1)


@cli.callback(invoke_without_command=True)
def principal(
    ctx: typer.Context,
    porta: Annotated[
        int | None, typer.Option(help="Porta local (padrão: a da configuração).")
    ] = None,
    navegador: Annotated[bool, typer.Option(help="Abrir o navegador ao subir.")] = True,
) -> None:
    """Sobe o JobFit e abre no navegador."""
    if ctx.invoked_subcommand:
        return
    porta = porta or carregar_config().porta
    url = f"http://{HOST}:{porta}"

    if porta_em_uso(porta):
        typer.echo(f"O JobFit já está aberto em {url}.")
        if navegador:
            webbrowser.open(url)
        return

    typer.echo(f"JobFit em {url} (feche esta janela ou use Ctrl+C para encerrar).")
    servidor = uvicorn.Server(configurar_servidor(porta))
    if navegador:
        threading.Thread(target=_abrir_quando_pronto, args=(servidor, url), daemon=True).start()
    servidor.run()


@cli.command("eval")
def avaliar_qualidade(
    perfil: Annotated[
        str | None, typer.Option(help="Perfil cuja IA (modo API) roda os evals; padrão: o último.")
    ] = None,
    conjunto: Annotated[
        list[str] | None,
        typer.Option(help="vagas, ataque, extracao ou perfil (repita para vários; padrão: todos)."),
    ] = None,
) -> None:
    """Mede a qualidade da IA com casos de resposta conhecida (sem cache; custa no modo API)."""
    import anyio  # só aqui: o comando principal não precisa disso

    from app import evals
    from app.db import banco_do_perfil
    from app.dossie.versoes import carregar_dossie
    from app.perfis.servico import ErroPerfil, carregar_perfil, pasta_perfil

    cfg = carregar_config()
    slug = perfil or cfg.ultimo_perfil
    if cfg.pasta_dados is None or not slug:
        typer.echo("Configure a pasta de dados e crie um perfil no app antes (uv run jobfit).")
        raise typer.Exit(1)
    escolhidos = conjunto or list(evals.CONJUNTOS)
    if desconhecidos := [c for c in escolhidos if c not in evals.CONJUNTOS]:
        typer.echo(f"Conjunto desconhecido: {', '.join(desconhecidos)}.")
        raise typer.Exit(2)
    try:
        dono = carregar_perfil(cfg.pasta_dados, slug)
    except ErroPerfil as erro:
        typer.echo(str(erro))
        raise typer.Exit(1) from erro
    engine = banco_do_perfil(slug)
    fatos = carregar_dossie(cfg.pasta_dados, engine, dono).fatos

    async def principal_eval():
        return await evals.rodar(dono, engine, escolhidos, fatos)

    try:
        resultados = anyio.run(principal_eval)
    except evals.ErroEval as erro:
        typer.echo(str(erro))
        raise typer.Exit(1) from erro
    texto = evals.relatorio(dono, resultados)
    destino = evals.salvar_relatorio(pasta_perfil(cfg.pasta_dados, slug), texto)
    typer.echo(texto)
    typer.echo(f"Relatório salvo em {destino}")


def main() -> None:
    cli()
