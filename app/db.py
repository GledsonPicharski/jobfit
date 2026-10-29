"""Um SQLite por perfil, migrado até a última versão sempre que é aberto."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Engine, create_engine, event

from app.config import caminho_banco
from app.perfis.servico import validar_slug

PASTA_MIGRACOES = Path(__file__).parent / "migracoes"

_engines: dict[Path, Engine] = {}


def _ativar_pragmas(conexao, _registro) -> None:
    cursor = conexao.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def config_alembic() -> Config:
    cfg = Config()
    # ConfigParser interpreta "%"; caminhos com "%" precisam ser escapados.
    cfg.set_main_option("script_location", str(PASTA_MIGRACOES).replace("%", "%%"))
    return cfg


def migrar(engine: Engine) -> None:
    cfg = config_alembic()
    with engine.begin() as conexao:
        cfg.attributes["connection"] = conexao
        command.upgrade(cfg, "head")


def abrir_banco(caminho: Path) -> Engine:
    caminho = caminho.resolve()
    if caminho in _engines:
        return _engines[caminho]
    caminho.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite", database=str(caminho)),
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _ativar_pragmas)
    migrar(engine)
    _engines[caminho] = engine
    return engine


def banco_do_perfil(slug: str) -> Engine:
    return abrir_banco(caminho_banco(validar_slug(slug)))


def fechar_bancos() -> None:
    """Libera os arquivos (no Windows, um SQLite aberto não pode ser apagado)."""
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()
