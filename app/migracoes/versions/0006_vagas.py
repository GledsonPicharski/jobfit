"""Vagas, avaliações e ajustes da pessoa.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-31 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_texto = sqlmodel.sql.sqltypes.AutoString
_data = sqlmodel.sql.sqltypes.UTCDateTime


def upgrade() -> None:
    op.create_table(
        "vagas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("criado_em", _data(), nullable=False),
        sa.Column("url", _texto(), nullable=True),
        sa.Column("fonte", _texto(), nullable=False),
        sa.Column("titulo", _texto(), nullable=True),
        sa.Column("empresa", _texto(), nullable=True),
        sa.Column("local", _texto(), nullable=True),
        sa.Column("modalidade", _texto(), nullable=True),
        sa.Column("senioridade", _texto(), nullable=True),
        sa.Column("idioma", _texto(), nullable=False),
        sa.Column("ingles", sa.Integer(), nullable=True),
        sa.Column("salario", _texto(), nullable=True),
        sa.Column("texto", _texto(), nullable=False),
        sa.Column("hash_texto", _texto(), nullable=False),
        sa.Column("estado", _texto(), nullable=False),
        sa.Column("faixa_esperada", _texto(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("vagas", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_vagas_criado_em"), ["criado_em"], unique=False)
        batch_op.create_index(batch_op.f("ix_vagas_url"), ["url"], unique=False)
        batch_op.create_index(batch_op.f("ix_vagas_hash_texto"), ["hash_texto"], unique=False)

    op.create_table(
        "avaliacoes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vaga_id", sa.Integer(), nullable=False),
        sa.Column("criado_em", _data(), nullable=False),
        sa.Column("versao_dossie", sa.Integer(), nullable=True),
        sa.Column("filtros", _texto(), nullable=False),
        sa.Column("bloqueada", sa.Boolean(), nullable=False),
        sa.Column("requisitos", _texto(), nullable=False),
        sa.Column("alertas", _texto(), nullable=False),
        sa.Column("nota", sa.Integer(), nullable=True),
        sa.Column("faixa", _texto(), nullable=True),
        sa.Column("recomenda", sa.Boolean(), nullable=True),
        sa.Column("chamada_id", sa.Integer(), nullable=True),
        sa.Column("versao_prompt", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["vaga_id"], ["vagas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("avaliacoes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_avaliacoes_vaga_id"), ["vaga_id"], unique=False)

    op.create_table(
        "ajustes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("avaliacao_id", sa.Integer(), nullable=False),
        sa.Column("requisito", sa.Integer(), nullable=False),
        sa.Column("acao", _texto(), nullable=False),
        sa.Column("texto", _texto(), nullable=True),
        sa.Column("fato_id", _texto(), nullable=True),
        sa.Column("criado_em", _data(), nullable=False),
        sa.ForeignKeyConstraint(["avaliacao_id"], ["avaliacoes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("ajustes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_ajustes_avaliacao_id"), ["avaliacao_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("ajustes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ajustes_avaliacao_id"))
    op.drop_table("ajustes")
    with op.batch_alter_table("avaliacoes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_avaliacoes_vaga_id"))
    op.drop_table("avaliacoes")
    with op.batch_alter_table("vagas", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_vagas_hash_texto"))
        batch_op.drop_index(batch_op.f("ix_vagas_url"))
        batch_op.drop_index(batch_op.f("ix_vagas_criado_em"))
    op.drop_table("vagas")
