"""Tabelas do dossiê no banco do perfil. O conteúdo fica no `dossie.md`; aqui, só o histórico."""

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.ia.modelos import agora_utc


class VersaoDossie(SQLModel, table=True):
    __tablename__ = "versoes_dossie"

    id: int | None = Field(default=None, primary_key=True)
    versao: int = Field(index=True, unique=True)
    criado_em: datetime = Field(default_factory=agora_utc)
    motivo: str  # criacao | edicao_manual | edicao_app | importacao
    importacao_id: int | None = None
    resumo: str = "{}"  # JSON: IDs adicionados, alterados e removidos
    sha256: str
