"""CVs por vaga: rascunho revisado e PDF.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-05 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_texto = sqlmodel.sql.sqltypes.AutoString
_data = sqlmodel.sql.sqltypes.UTCDateTime


def upgrade() -> None:
    op.create_table(
        "cvs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vaga_id", sa.Integer(), nullable=True),
        sa.Column("idioma", _texto(), nullable=False),
        sa.Column("criado_em", _data(), nullable=False),
        sa.Column("atualizado_em", _data(), nullable=False),
        sa.Column("estado", _texto(), nullable=False),
        sa.Column("conteudo", _texto(), nullable=False),
        sa.Column("alertas", _texto(), nullable=False),
        sa.Column("versao_dossie", sa.Integer(), nullable=True),
        sa.Column("chamada_id", sa.Integer(), nullable=True),
        sa.Column("versao_prompt", sa.Integer(), nullable=True),
        sa.Column("arquivo_pdf", _texto(), nullable=True),
        sa.Column("paginas", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["vaga_id"], ["vagas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("cvs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_cvs_vaga_id"), ["vaga_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("cvs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_cvs_vaga_id"))
    op.drop_table("cvs")
