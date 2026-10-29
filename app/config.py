"""Configuração global do app e caminhos da máquina.

Fica em `%LOCALAPPDATA%\\JobFit` (fora do Google Drive): `config.json` e os bancos
SQLite de cada perfil, em `bancos\\<slug>.db`. Sincronização em nuvem pode corromper um
SQLite aberto; só os backups vão para a pasta de dados.
"""

import os
from pathlib import Path

from platformdirs import user_data_path
from pydantic import BaseModel

from app.arquivos import gravar_texto, ler_texto

PORTA_PADRAO = 8765


class AppConfig(BaseModel):
    pasta_dados: Path | None = None
    porta: int = PORTA_PADRAO
    ultimo_perfil: str | None = None


def pasta_app() -> Path:
    """`JOBFIT_HOME` sobrescreve o padrão (testes e desenvolvimento)."""
    if sobrescrita := os.environ.get("JOBFIT_HOME"):
        return Path(sobrescrita)
    return user_data_path("JobFit", appauthor=False, roaming=False)


def caminho_config() -> Path:
    return pasta_app() / "config.json"


def caminho_banco(slug: str) -> Path:
    return pasta_app() / "bancos" / f"{slug}.db"


def carregar_config() -> AppConfig:
    caminho = caminho_config()
    if not caminho.exists():
        return AppConfig()
    return AppConfig.model_validate_json(ler_texto(caminho))


def salvar_config(cfg: AppConfig) -> None:
    gravar_texto(caminho_config(), cfg.model_dump_json(indent=2) + "\n")
