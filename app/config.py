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


class ErroConfig(ValueError):
    pass


def validar_pasta_dados(texto: str) -> Path:
    """Aceita o caminho como o Windows copia (entre aspas), cria a pasta e testa a escrita."""
    texto = texto.strip().strip('"').strip()
    if not texto:
        raise ErroConfig("Informe a pasta de dados.")
    pasta = Path(texto).expanduser()
    if not pasta.is_absolute():
        raise ErroConfig(
            f"Use o caminho completo da pasta, por exemplo C:\\JobFit (recebido: {texto})."
        )
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        teste = pasta / ".jobfit-teste-escrita"
        gravar_texto(teste, "ok")
        teste.unlink()
    except OSError as erro:
        raise ErroConfig(f"Não consegui gravar em {pasta}: {erro.strerror or erro}.") from erro
    return pasta


def carregar_config() -> AppConfig:
    caminho = caminho_config()
    if not caminho.exists():
        return AppConfig()
    return AppConfig.model_validate_json(ler_texto(caminho))


def salvar_config(cfg: AppConfig) -> None:
    gravar_texto(caminho_config(), cfg.model_dump_json(indent=2) + "\n")
