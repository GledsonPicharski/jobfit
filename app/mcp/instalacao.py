"""Ligar o JobFit ao Claude Desktop: a entrada `mcpServers.jobfit` do `claude_desktop_config.json`.

Só essa entrada é tocada; o resto do arquivo (outros servidores, preferências) fica como
estava, e uma cópia `.bak` é feita antes de gravar. Na versão da Microsoft Store, o
Claude Desktop lê o arquivo de dentro da pasta do pacote, não de `%APPDATA%\\Claude`.
"""

import json
import os
import shutil
import sys
from pathlib import Path

from app.arquivos import gravar_texto

NOME = "jobfit"
ARQUIVO = "claude_desktop_config.json"


class ErroInstalacao(ValueError):
    pass


def caminhos_possiveis(
    localappdata: Path | None = None, appdata: Path | None = None, casa: Path | None = None
) -> list[Path]:
    """Onde o Claude Desktop pode ler a configuração, do mais provável ao menos.

    `JOBFIT_CLAUDE_CONFIG` sobrescreve (testes: nunca tocar no arquivo real da pessoa).
    """
    if not (localappdata or appdata or casa) and (fixo := os.environ.get("JOBFIT_CLAUDE_CONFIG")):
        return [Path(fixo)]
    if sys.platform == "win32" or localappdata or appdata:
        local = localappdata or Path(os.environ.get("LOCALAPPDATA", ""))
        roaming = appdata or Path(os.environ.get("APPDATA", ""))
        pacotes = sorted((local / "Packages").glob("Claude_*")) if local.parts else []
        return [p / "LocalCache" / "Roaming" / "Claude" / ARQUIVO for p in pacotes] + [
            roaming / "Claude" / ARQUIVO
        ]
    casa = casa or Path.home()
    if sys.platform == "darwin":
        return [casa / "Library" / "Application Support" / "Claude" / ARQUIVO]
    return [casa / ".config" / "Claude" / ARQUIVO]


def achar_config(candidatos: list[Path] | None = None) -> Path | None:
    """O arquivo que já existe; senão, onde a pasta do Claude já existe; senão, nenhum."""
    candidatos = caminhos_possiveis() if candidatos is None else candidatos
    for caminho in candidatos:
        if caminho.is_file():
            return caminho
    for caminho in candidatos:
        # o pacote da Store só entra na lista se estiver instalado
        if caminho.parent.is_dir() or "Packages" in caminho.parts:
            return caminho
    return None


def entrada(slug: str) -> dict:
    """O Python do ambiente do JobFit, sem `uv run`: não trava a sincronização do uv."""
    return {
        "command": sys.executable,
        "args": ["-m", "app.mcp", "--perfil", slug],
        "env": {"PYTHONIOENCODING": "utf-8"},
    }


def _ler(caminho: Path) -> dict:
    if not caminho.is_file():
        return {}
    texto = caminho.read_text(encoding="utf-8-sig").strip()
    if not texto:
        return {}
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as erro:
        raise ErroInstalacao(
            f"O arquivo de configuração do Claude Desktop ({caminho}) não é um JSON válido; "
            "corrija-o antes, para o JobFit não apagar o que está nele."
        ) from erro
    if not isinstance(dados, dict):
        raise ErroInstalacao(f"O arquivo {caminho} não tem o formato esperado.")
    return dados


def _gravar(caminho: Path, dados: dict) -> None:
    if caminho.is_file():
        shutil.copy2(caminho, caminho.with_name(caminho.name + ".bak"))
    caminho.parent.mkdir(parents=True, exist_ok=True)
    gravar_texto(caminho, json.dumps(dados, ensure_ascii=False, indent=2) + "\n")


def conectado(caminho: Path) -> str | None:
    """O perfil ligado ao Claude Desktop, ou None."""
    try:
        servidor = _ler(caminho).get("mcpServers", {}).get(NOME)
    except ErroInstalacao:
        return None
    if not isinstance(servidor, dict):
        return None
    args = servidor.get("args", [])
    return args[args.index("--perfil") + 1] if "--perfil" in args[:-1] else ""


def instalar(caminho: Path, slug: str) -> None:
    dados = _ler(caminho)
    servidores = dados.setdefault("mcpServers", {})
    if not isinstance(servidores, dict):
        raise ErroInstalacao(f'"mcpServers" em {caminho} não tem o formato esperado.')
    servidores[NOME] = entrada(slug)
    _gravar(caminho, dados)


def remover(caminho: Path) -> bool:
    dados = _ler(caminho)
    servidores = dados.get("mcpServers")
    if not isinstance(servidores, dict) or NOME not in servidores:
        return False
    del servidores[NOME]
    _gravar(caminho, dados)
    return True
