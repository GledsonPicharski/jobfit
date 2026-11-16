"""Scan diário pelo Agendador de Tarefas do Windows (`jobfit agendar`), não cron.

A tarefa roda o mesmo Python do ambiente do JobFit, sem `uv run` nem `jobfit.exe`, que
travam com o app aberto (aprendizado da Fase 1, como no MCP). Usa o `pythonw.exe`, que não
abre janela de terminal; o resultado fica registrado na tela Buscas.
"""

import re
import subprocess
import sys
from pathlib import Path

_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ErroAgendamento(ValueError):
    pass


def nome_tarefa(slug: str) -> str:
    return f"JobFit scan ({slug})"


def executavel(python: Path) -> Path:
    """O `pythonw.exe` ao lado do Python do ambiente, se existir: sem janela."""
    sem_janela = python.with_name("pythonw.exe")
    return sem_janela if sem_janela.is_file() else python


def comando_criar(slug: str, hora: str, programa: Path | None = None) -> list[str]:
    if not _HORA.match(hora):
        raise ErroAgendamento(f"Use a hora no formato HH:MM (ex.: 08:00), não {hora!r}.")
    programa = programa or executavel(Path(sys.executable))
    acao = f'"{programa}" -m app.cli scan --perfil {slug} --agendada'
    return [
        "schtasks", "/Create", "/F", "/SC", "DAILY", "/ST", hora,
        "/TN", nome_tarefa(slug), "/TR", acao,
    ]  # fmt: skip


def comando_remover(slug: str) -> list[str]:
    return ["schtasks", "/Delete", "/F", "/TN", nome_tarefa(slug)]


def rodar(comando: list[str]) -> None:
    resultado = subprocess.run(comando, capture_output=True, text=True, check=False)
    if resultado.returncode != 0:
        detalhe = (resultado.stderr or resultado.stdout).strip()
        raise ErroAgendamento(f"O Agendador de Tarefas recusou: {detalhe}")
