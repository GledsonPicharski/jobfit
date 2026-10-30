"""Histórico de versões do dossiê (versoes_dossie).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-30 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "versoes_dossie",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("criado_em", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.Column("motivo", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("importacao_id", sa.Integer(), nullable=True),
        sa.Column("resumo", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("sha256", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("versoes_dossie", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_versoes_dossie_versao"), ["versao"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("versoes_dossie", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_versoes_dossie_versao"))

    op.drop_table("versoes_dossie")
