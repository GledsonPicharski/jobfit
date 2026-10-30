"""Pedidos do modo manual (pedidos_ia).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29 22:51:21.112904
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pedidos_ia",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("criado_em", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column("tarefa", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("versao_prompt", sa.Integer(), nullable=False),
        sa.Column("provedor", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("modelo", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("chave_cache", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("pacote", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("tentativas", sa.Integer(), nullable=False),
        sa.Column("respondido_em", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pedidos_ia", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_pedidos_ia_chave_cache"), ["chave_cache"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_pedidos_ia_criado_em"), ["criado_em"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("pedidos_ia", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_pedidos_ia_criado_em"))
        batch_op.drop_index(batch_op.f("ix_pedidos_ia_chave_cache"))

    op.drop_table("pedidos_ia")
