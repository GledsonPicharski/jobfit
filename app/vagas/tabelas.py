"""Vagas no banco do perfil: a cópia da vaga, as avaliações e os ajustes da pessoa."""

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.ia.modelos import agora_utc


class Vaga(SQLModel, table=True):
    __tablename__ = "vagas"

    id: int | None = Field(default=None, primary_key=True)
    criado_em: datetime = Field(default_factory=agora_utc, index=True)
    url: str | None = Field(default=None, index=True)  # normalizada
    fonte: str  # greenhouse | lever | gupy | pagina | texto
    titulo: str | None = None
    empresa: str | None = None
    local: str | None = None
    modalidade: str | None = None
    senioridade: str | None = None
    idioma: str = "pt"
    ingles: int | None = None
    salario: str | None = None  # JSON: moeda, minimo e maximo por mês
    texto: str  # a cópia da vaga: continua aqui se ela sair do ar
    hash_texto: str = Field(index=True)
    estado: str = "avaliada"  # avaliada | quero_aplicar | descartada (a Fase 5 amplia)
    faixa_esperada: str | None = None  # a faixa que a pessoa daria (concordância)


class Avaliacao(SQLModel, table=True):
    __tablename__ = "avaliacoes"

    id: int | None = Field(default=None, primary_key=True)
    vaga_id: int = Field(foreign_key="vagas.id", index=True)
    criado_em: datetime = Field(default_factory=agora_utc)
    versao_dossie: int | None = None
    filtros: str = "{}"  # JSON: bloqueios e alertas
    bloqueada: bool = False  # barrada pelos filtros, sem chamar a IA
    requisitos: str = "[]"  # JSON: requisitos julgados, já conferidos em código
    alertas: str = "[]"  # JSON: o que a checagem depois da IA corrigiu
    nota: int | None = None
    faixa: str | None = None
    recomenda: bool | None = None
    chamada_id: int | None = None
    versao_prompt: int | None = None


class Ajuste(SQLModel, table=True):
    """O que a pessoa disse sobre um requisito: muda a nota sem nova chamada de IA."""

    __tablename__ = "ajustes"

    id: int | None = Field(default=None, primary_key=True)
    avaliacao_id: int = Field(foreign_key="avaliacoes.id", index=True)
    requisito: int  # posição na lista de requisitos da avaliação
    acao: str  # tenho | nao_tenho | nao_se_aplica | nao_e_bem_assim
    texto: str | None = None
    fato_id: str | None = None  # o fato criado por "eu tenho isso"
    criado_em: datetime = Field(default_factory=agora_utc)
