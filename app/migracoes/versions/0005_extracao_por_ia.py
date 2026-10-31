"""Importações com texto para a IA (extraido) e a etapa de extração (extracao).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-30 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("importacoes", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("extraido", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("extracao", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("importacoes", schema=None) as batch_op:
        batch_op.drop_column("extracao")
        batch_op.drop_column("extraido")
