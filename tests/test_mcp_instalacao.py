"""Ligar ao Claude Desktop sem estragar o arquivo de configuração da pessoa."""

import json
import sys
from pathlib import Path

import pytest

from app.mcp.instalacao import (
    ErroInstalacao,
    achar_config,
    caminhos_possiveis,
    conectado,
    instalar,
    remover,
)


@pytest.fixture
def pastas(tmp_path):
    """%LOCALAPPDATA% e %APPDATA% falsos, com espaço e acento."""
    local = tmp_path / "Usuário Teste" / "AppData" / "Local"
    roaming = tmp_path / "Usuário Teste" / "AppData" / "Roaming"
    local.mkdir(parents=True)
    roaming.mkdir(parents=True)
    return local, roaming


def _ler(caminho):
    return json.loads(caminho.read_text(encoding="utf-8"))


def test_versao_da_store_vem_antes_da_do_instalador(pastas):
    local, roaming = pastas
    (local / "Packages" / "Claude_pzs8sxrjxfjjc" / "LocalCache" / "Roaming").mkdir(parents=True)
    candidatos = caminhos_possiveis(localappdata=local, appdata=roaming)
    assert candidatos[0].parts[-5:] == (
        "Claude_pzs8sxrjxfjjc",
        "LocalCache",
        "Roaming",
        "Claude",
        "claude_desktop_config.json",
    )
    assert achar_config(candidatos) == candidatos[0]


def test_dados_movidos_para_fora_do_pacote_vem_primeiro(pastas):
    """Versões recentes da Store movem os dados para %LOCALAPPDATA%\\Claude-Data\\claude_<id>."""
    local, roaming = pastas
    (local / "Packages" / "Claude_pzs8sxrjxfjjc" / "LocalCache" / "Roaming" / "Claude").mkdir(
        parents=True
    )
    movidos = local / "Claude-Data" / "claude_pzs8sxrjxfjjc"
    movidos.mkdir(parents=True)
    candidatos = caminhos_possiveis(localappdata=local, appdata=roaming)
    assert candidatos[0] == movidos / "claude_desktop_config.json"
    assert achar_config(candidatos) == candidatos[0]

    # mesmo que um arquivo antigo tenha ficado na pasta do pacote
    antigo = candidatos[1]
    antigo.write_text("{}", encoding="utf-8")
    (movidos / "claude_desktop_config.json").write_text("{}", encoding="utf-8")
    assert achar_config(candidatos) == candidatos[0]


def test_versao_do_instalador_e_sem_claude(pastas):
    local, roaming = pastas
    candidatos = caminhos_possiveis(localappdata=local, appdata=roaming)
    assert candidatos == [roaming / "Claude" / "claude_desktop_config.json"]
    assert achar_config(candidatos) is None  # sem Claude Desktop instalado
    (roaming / "Claude").mkdir()
    assert achar_config(candidatos) == candidatos[0]


def test_arquivo_que_ja_existe_tem_preferencia(pastas):
    local, roaming = pastas
    (local / "Packages" / "Claude_x").mkdir(parents=True)
    existente = roaming / "Claude" / "claude_desktop_config.json"
    existente.parent.mkdir()
    existente.write_text("{}", encoding="utf-8")
    assert achar_config(caminhos_possiveis(localappdata=local, appdata=roaming)) == existente


def test_instalar_em_arquivo_novo(pastas):
    caminho = pastas[1] / "Claude" / "claude_desktop_config.json"
    instalar(caminho, "ana")
    servidor = _ler(caminho)["mcpServers"]["jobfit"]
    assert servidor["command"] == sys.executable
    assert servidor["args"] == ["-m", "app.mcp", "--perfil", "ana"]
    assert conectado(caminho) == "ana"
    assert not caminho.with_name("claude_desktop_config.json.bak").exists()


def test_instalar_preserva_o_resto_e_faz_copia(pastas):
    caminho = pastas[1] / "Claude" / "claude_desktop_config.json"
    caminho.parent.mkdir()
    original = {
        "mcpServers": {"outro": {"command": "npx", "args": ["servidor-ç"]}},
        "preferencias": {"tema": "escuro — sempre"},
    }
    caminho.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

    instalar(caminho, "ana")
    instalar(caminho, "bia")  # de novo: atualiza, não duplica
    dados = _ler(caminho)
    assert dados["mcpServers"]["outro"] == original["mcpServers"]["outro"]
    assert dados["preferencias"] == original["preferencias"]
    assert set(dados["mcpServers"]) == {"outro", "jobfit"}
    assert conectado(caminho) == "bia"
    assert "outro" in _ler(caminho.with_name("claude_desktop_config.json.bak"))["mcpServers"]

    assert remover(caminho) is True
    assert _ler(caminho)["mcpServers"] == {"outro": original["mcpServers"]["outro"]}
    assert conectado(caminho) is None
    assert remover(caminho) is False


def test_json_quebrado_nao_e_sobrescrito(pastas):
    caminho = pastas[1] / "Claude" / "claude_desktop_config.json"
    caminho.parent.mkdir()
    caminho.write_text('{"mcpServers": {', encoding="utf-8")
    with pytest.raises(ErroInstalacao, match="não é um JSON válido"):
        instalar(caminho, "ana")
    assert caminho.read_text(encoding="utf-8") == '{"mcpServers": {'
    assert conectado(caminho) is None


def test_arquivo_com_bom_e_vazio(pastas):
    caminho = pastas[1] / "Claude" / "claude_desktop_config.json"
    caminho.parent.mkdir()
    caminho.write_text("﻿{}", encoding="utf-8")
    instalar(caminho, "ana")
    assert conectado(caminho) == "ana"
    caminho.write_text("", encoding="utf-8")
    instalar(caminho, "ana")
    assert conectado(caminho) == "ana"


def test_conectar_e_desconectar_pela_tela(pasta_dados):
    import os

    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.perfis.servico import criar_perfil

    criar_perfil(pasta_dados, "Ana Exemplo", "ana")
    origem = "http://127.0.0.1:8765"
    cliente = TestClient(create_app(), base_url=origem, headers={"Origin": origem})
    arquivo = Path(os.environ["JOBFIT_CLAUDE_CONFIG"])  # do conftest: nunca o real

    assert "Não encontrei o Claude Desktop" in cliente.get("/p/ana/ia").text
    arquivo.parent.mkdir(parents=True)
    assert "Conectar ao Claude Desktop" in cliente.get("/p/ana/ia").text

    tela = cliente.post("/p/ana/ia/claude-desktop", data={"acao": "conectar"}).text
    assert "Ligado. Feche o Claude Desktop" in tela and "Ligado a este perfil" in tela
    assert conectado(arquivo) == "ana"

    tela = cliente.post("/p/ana/ia/claude-desktop", data={"acao": "desconectar"}).text
    assert "Desligado" in tela and "Conectar ao Claude Desktop" in tela
    assert conectado(arquivo) is None


def test_cli_instalar_e_remover(pasta_dados):
    import os

    from typer.testing import CliRunner

    from app import config
    from app.cli import cli

    config.salvar_config(config.carregar_config().model_copy(update={"ultimo_perfil": "ana"}))
    arquivo = Path(os.environ["JOBFIT_CLAUDE_CONFIG"])
    arquivo.parent.mkdir(parents=True)
    saida = CliRunner().invoke(cli, ["mcp", "instalar"])
    assert saida.exit_code == 0 and "Perfil ana ligado" in saida.output
    assert conectado(arquivo) == "ana"
    saida = CliRunner().invoke(cli, ["mcp", "remover"])
    assert "desligado" in saida.output and conectado(arquivo) is None
