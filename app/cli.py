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


def main() -> None:
    cli()
