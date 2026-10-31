"""Ambiente do Alembic.

O app passa a conexão do banco do perfil em `config.attributes["connection"]`
(ver `app/db.py`). Para gerar migrações em desenvolvimento:

    uv run alembic revision --autogenerate -m "descrição"

que usa um banco temporário em `sqlalchemy.url` do `alembic.ini`.
"""

from alembic import context
from sqlalchemy import create_engine
from sqlmodel import SQLModel

import app.dossie.tabelas  # noqa: F401  (registra as tabelas no metadata)
import app.ia.modelos  # noqa: F401
import app.vagas.tabelas  # noqa: F401

alvo = SQLModel.metadata


def _rodar(conexao) -> None:
    # render_as_batch: o SQLite não altera colunas no lugar; o Alembic recria a tabela.
    context.configure(connection=conexao, target_metadata=alvo, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


conexao = context.config.attributes.get("connection")
if conexao is not None:
    _rodar(conexao)
else:
    engine = create_engine(context.config.get_main_option("sqlalchemy.url"))
    with engine.begin() as nova:
        _rodar(nova)
