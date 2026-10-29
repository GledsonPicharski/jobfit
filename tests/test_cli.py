import socket

import pytest
from typer.testing import CliRunner

from app import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def navegador(monkeypatch):
    abertos: list[str] = []
    monkeypatch.setattr(cli.webbrowser, "open", abertos.append)
    return abertos


def test_ajuda(runner):
    resultado = runner.invoke(cli.cli, ["--help"])
    assert resultado.exit_code == 0
    assert "--porta" in resultado.output


def test_servidor_so_escuta_em_localhost():
    config = cli.configurar_servidor(8765)
    assert config.host == "127.0.0.1"
    assert config.port == 8765


def test_porta_ocupada_so_abre_o_navegador(runner, navegador, monkeypatch):
    def nao_subir(*_):
        raise AssertionError("não devia subir outro servidor")

    with socket.socket() as ocupante:
        ocupante.bind(("127.0.0.1", 0))
        ocupante.listen()
        porta = ocupante.getsockname()[1]
        monkeypatch.setattr(cli.uvicorn.Server, "run", nao_subir)

        resultado = runner.invoke(cli.cli, ["--porta", str(porta)])

    assert resultado.exit_code == 0
    assert "já está aberto" in resultado.output
    assert navegador == [f"http://127.0.0.1:{porta}"]


def test_sobe_servidor_na_porta_da_configuracao(runner, navegador, monkeypatch):
    usadas = []
    monkeypatch.setattr(cli, "porta_em_uso", lambda _porta: False)
    monkeypatch.setattr(cli.uvicorn.Server, "run", lambda self: usadas.append(self.config.port))

    resultado = runner.invoke(cli.cli, ["--no-navegador"])

    assert resultado.exit_code == 0, resultado.output
    assert usadas == [8765]
    assert navegador == []
