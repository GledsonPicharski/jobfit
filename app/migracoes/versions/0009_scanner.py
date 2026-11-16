"""Scanner de portais: origens das vagas, buscas salvas, varreduras e portais por perfil.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-15 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_texto = sqlmodel.sql.sqltypes.AutoString
_data = sqlmodel.sql.sqltypes.UTCDateTime


def upgrade() -> None:
    with op.batch_alter_table("vagas", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prenota", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("publicada_em", _data(), nullable=True))
        batch_op.add_column(sa.Column("aberta", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("checada_em", _data(), nullable=True))
        batch_op.add_column(sa.Column("encerrada_em", _data(), nullable=True))

    op.create_table(
        "buscas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", _texto(), nullable=False),
        sa.Column("titulos", _texto(), nullable=False),
        sa.Column("so_remoto", sa.Boolean(), nullable=False),
        sa.Column("paises", _texto(), nullable=False),
        sa.Column("senioridades", _texto(), nullable=False),
        sa.Column("salario_minimo", sa.Integer(), nullable=True),
        sa.Column("empresas_excluidas", _texto(), nullable=False),
        sa.Column("setores_excluidos", _texto(), nullable=False),
        sa.Column("palavras_obrigatorias", _texto(), nullable=False),
        sa.Column("palavras_proibidas", _texto(), nullable=False),
        sa.Column("portais", _texto(), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False),
        sa.Column("criado_em", _data(), nullable=False),
        sa.Column("atualizado_em", _data(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "vaga_origens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vaga_id", sa.Integer(), nullable=False),
        sa.Column("portal", _texto(), nullable=False),
        sa.Column("url", _texto(), nullable=True),
        sa.Column("busca_id", sa.Integer(), nullable=True),
        sa.Column("primeira_vez", _data(), nullable=False),
        sa.Column("ultima_vez", _data(), nullable=False),
        sa.ForeignKeyConstraint(["vaga_id"], ["vagas.id"]),
        sa.ForeignKeyConstraint(["busca_id"], ["buscas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("vaga_origens", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_vaga_origens_vaga_id"), ["vaga_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_vaga_origens_portal"), ["portal"], unique=False)
    op.create_table(
        "varreduras",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inicio", _data(), nullable=False),
        sa.Column("fim", _data(), nullable=True),
        sa.Column("origem", _texto(), nullable=False),
        sa.Column("estado", _texto(), nullable=False),
        sa.Column("portais", _texto(), nullable=False),
        sa.Column("novas", sa.Integer(), nullable=False),
        sa.Column("erros", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("varreduras", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_varreduras_inicio"), ["inicio"], unique=False)
    op.create_table(
        "consultas_portal",
        sa.Column("chave", _texto(), nullable=False),
        sa.Column("feita_em", _data(), nullable=False),
        sa.PrimaryKeyConstraint("chave"),
    )
    op.create_table(
        "portais_perfil",
        sa.Column("portal", _texto(), nullable=False),
        sa.Column("desligado", sa.Boolean(), nullable=False),
        sa.Column("cadastro", _texto(), nullable=True),
        sa.Column("frequencia_dias", sa.Integer(), nullable=True),
        sa.Column("ultima_checagem", _data(), nullable=True),
        sa.Column("observacoes", _texto(), nullable=True),
        sa.PrimaryKeyConstraint("portal"),
    )

    # As vagas que já existem foram coladas pela pessoa: cada uma ganha essa origem.
    op.execute(
        "INSERT INTO vaga_origens (vaga_id, portal, url, primeira_vez, ultima_vez) "
        "SELECT id, 'colada', url, criado_em, criado_em FROM vagas"
    )


def downgrade() -> None:
    op.drop_table("portais_perfil")
    op.drop_table("consultas_portal")
    with op.batch_alter_table("varreduras", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_varreduras_inicio"))
    op.drop_table("varreduras")
    with op.batch_alter_table("vaga_origens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_vaga_origens_portal"))
        batch_op.drop_index(batch_op.f("ix_vaga_origens_vaga_id"))
    op.drop_table("vaga_origens")
    op.drop_table("buscas")
    with op.batch_alter_table("vagas", schema=None) as batch_op:
        batch_op.drop_column("encerrada_em")
        batch_op.drop_column("checada_em")
        batch_op.drop_column("aberta")
        batch_op.drop_column("publicada_em")
        batch_op.drop_column("prenota")
