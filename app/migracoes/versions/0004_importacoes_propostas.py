"""Importações e propostas de alteração do dossiê.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-30 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_texto = sqlmodel.sql.sqltypes.AutoString


def upgrade() -> None:
    op.create_table(
        "importacoes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("criado_em", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column("fonte", _texto(), nullable=False),
        sa.Column("nome", _texto(), nullable=False),
        sa.Column("arquivo", _texto(), nullable=True),
        sa.Column("status", _texto(), nullable=False),
        sa.Column("versao_aplicada", sa.Integer(), nullable=True),
        sa.Column("duplicados", sa.Integer(), nullable=False),
        sa.Column("ja_rejeitados", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("importacoes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_importacoes_criado_em"), ["criado_em"], unique=False)

    op.create_table(
        "propostas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("importacao_id", sa.Integer(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("acao", _texto(), nullable=False),
        sa.Column("fato_alvo", _texto(), nullable=True),
        sa.Column("dados", _texto(), nullable=False),
        sa.Column("chave", _texto(), nullable=False),
        sa.Column("trecho", _texto(), nullable=True),
        sa.Column("alertas", _texto(), nullable=False),
        sa.Column("sugestao", _texto(), nullable=False),
        sa.Column("motivo", _texto(), nullable=False),
        sa.Column("decisao", _texto(), nullable=False),
        sa.Column("dados_editados", _texto(), nullable=True),
        sa.ForeignKeyConstraint(["importacao_id"], ["importacoes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("propostas", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_propostas_chave"), ["chave"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_propostas_importacao_id"), ["importacao_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("propostas", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_propostas_importacao_id"))
        batch_op.drop_index(batch_op.f("ix_propostas_chave"))
    op.drop_table("propostas")
    with op.batch_alter_table("importacoes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_importacoes_criado_em"))
    op.drop_table("importacoes")
