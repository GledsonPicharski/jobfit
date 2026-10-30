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


class Importacao(SQLModel, table=True):
    """Uma entrada (PDF do LinkedIn, CV, texto) e o lote de propostas que ela gerou."""

    __tablename__ = "importacoes"

    id: int | None = Field(default=None, primary_key=True)
    criado_em: datetime = Field(default_factory=agora_utc, index=True)
    fonte: str  # linkedin_pdf | cv | texto
    nome: str  # nome do arquivo ou descrição curta, para a tela
    arquivo: str | None = None  # caminho relativo à pasta do perfil (em fontes/)
    status: str = "revisao"  # extraindo | revisao | aplicada | descartada
    versao_aplicada: int | None = None
    duplicados: int = 0
    ja_rejeitados: int = 0


class Proposta(SQLModel, table=True):
    __tablename__ = "propostas"

    id: int | None = Field(default=None, primary_key=True)
    importacao_id: int = Field(foreign_key="importacoes.id", index=True)
    ordem: int
    acao: str  # novo | alterar | conflito
    fato_alvo: str | None = None  # ID do fato do dossiê em alterar/conflito
    dados: str  # JSON do candidato (campos do fato, sem id)
    chave: str = Field(index=True)  # tipo + texto normalizado, para não propor de novo
    trecho: str | None = None
    alertas: str = "[]"  # JSON
    sugestao: str  # aprovar | rejeitar | manter_atual | usar_nova
    motivo: str = ""
    decisao: str = "pendente"  # pendente | aprovada | editada | rejeitada
    dados_editados: str | None = None  # JSON
