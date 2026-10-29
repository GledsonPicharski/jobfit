"""Inicial: chamadas_ia e cache_ia.

Revision ID: 0001
Revises:
Create Date: 2026-10-29 19:44:24.265336
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cache_ia",
        sa.Column("chave", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tarefa", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("versao_prompt", sa.Integer(), nullable=False),
        sa.Column("modelo", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("saida_json", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("criado_em", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("chave"),
    )
    op.create_table(
        "chamadas_ia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("criado_em", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column("tarefa", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("versao_prompt", sa.Integer(), nullable=False),
        sa.Column("provedor", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("modelo", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tokens_entrada", sa.Integer(), nullable=False),
        sa.Column("tokens_saida", sa.Integer(), nullable=False),
        sa.Column("custo_micro_usd", sa.Integer(), nullable=True),
        sa.Column("duracao_ms", sa.Integer(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("sucesso", sa.Boolean(), nullable=False),
        sa.Column("erro", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("chamadas_ia", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_chamadas_ia_criado_em"), ["criado_em"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("chamadas_ia", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chamadas_ia_criado_em"))

    op.drop_table("chamadas_ia")
    op.drop_table("cache_ia")
