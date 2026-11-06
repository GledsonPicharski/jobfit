"""CVs no banco do perfil: o rascunho revisado e o PDF gerado."""

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.ia.modelos import agora_utc


class CV(SQLModel, table=True):
    __tablename__ = "cvs"

    id: int | None = Field(default=None, primary_key=True)
    vaga_id: int | None = Field(default=None, foreign_key="vagas.id", index=True)
    idioma: str  # pt | en
    criado_em: datetime = Field(default_factory=agora_utc)
    atualizado_em: datetime = Field(default_factory=agora_utc)
    estado: str = "rascunho"  # rascunho | pronto (PDF gerado sem bloqueios)
    conteudo: str  # JSON do Rascunho: a estrutura do código com as frases da IA e as edições
    alertas: str = "[]"  # JSON: o que a checagem corrigiu ao receber a saída da IA
    versao_dossie: int | None = None
    chamada_id: int | None = None
    versao_prompt: int | None = None
    arquivo_pdf: str | None = None  # relativo à pasta do perfil
    paginas: int | None = None
