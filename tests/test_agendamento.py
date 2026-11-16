"""`jobfit agendar`: a tarefa diária do scan no Agendador de Tarefas do Windows."""

import sys
from pathlib import Path

import pytest

from app.agendamento import ErroAgendamento, comando_criar, comando_remover, executavel, nome_tarefa


def test_comando_de_criar_usa_o_python_do_ambiente_sem_janela():
    programa = Path(r"C:\Users\Usuário Teste\Meu Projeto\.venv\Scripts\pythonw.exe")
    comando = comando_criar("ana", "08:30", programa=programa)
    assert comando[:2] == ["schtasks", "/Create"]
    assert comando[comando.index("/TN") + 1] == "JobFit scan (ana)"
    assert comando[comando.index("/SC") + 1] == "DAILY"
    assert comando[comando.index("/ST") + 1] == "08:30"
    acao = comando[comando.index("/TR") + 1]
    assert acao == (
        r'"C:\Users\Usuário Teste\Meu Projeto\.venv\Scripts\pythonw.exe" '
        "-m app.cli scan --perfil ana --agendada"
    )
    assert "/F" in comando  # agendar de novo troca o horário


def test_comando_de_remover():
    assert comando_remover("ana") == ["schtasks", "/Delete", "/F", "/TN", "JobFit scan (ana)"]


@pytest.mark.parametrize("hora", ["8h", "25:00", "08:60", ""])
def test_hora_invalida(hora):
    with pytest.raises(ErroAgendamento, match="hora"):
        comando_criar("ana", hora, programa=Path("pythonw.exe"))


def test_executavel_prefere_o_sem_janela(tmp_path):
    python = tmp_path / "python.exe"
    python.touch()
    assert executavel(python) == python  # sem pythonw ao lado, usa o python
    (tmp_path / "pythonw.exe").touch()
    assert executavel(python) == tmp_path / "pythonw.exe"


def test_nome_da_tarefa_por_perfil():
    assert nome_tarefa("bia") == "JobFit scan (bia)"


def test_cli_agendar_monta_e_roda_o_comando(pasta_dados, monkeypatch):
    from typer.testing import CliRunner

    from app import agendamento, config
    from app.cli import cli

    config.salvar_config(config.carregar_config().model_copy(update={"ultimo_perfil": "ana"}))
    rodados = []
    monkeypatch.setattr(agendamento, "rodar", lambda comando: rodados.append(comando))
    monkeypatch.setattr(sys, "platform", "win32")

    saida = CliRunner().invoke(cli, ["agendar", "--hora", "07:15"])
    assert saida.exit_code == 0, saida.output
    assert "todo dia às 07:15" in saida.output
    assert rodados[0][1] == "/Create"
    saida = CliRunner().invoke(cli, ["agendar", "--remover"])
    assert "removido" in saida.output and rodados[1][1] == "/Delete"


def test_cli_agendar_fora_do_windows(pasta_dados, monkeypatch):
    from typer.testing import CliRunner

    from app import config
    from app.cli import cli

    config.salvar_config(config.carregar_config().model_copy(update={"ultimo_perfil": "ana"}))
    monkeypatch.setattr(sys, "platform", "linux")
    saida = CliRunner().invoke(cli, ["agendar"])
    assert saida.exit_code == 1 and "Agendador de Tarefas do Windows" in saida.output
