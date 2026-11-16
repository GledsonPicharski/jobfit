"""Pedidos do modo manual: por onde veio a resposta (chat colado ou Claude Desktop).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-06 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("pedidos_ia", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("respondido_por", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("pedidos_ia", schema=None) as batch_op:
        batch_op.drop_column("respondido_por")
