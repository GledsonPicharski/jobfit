"""Tabelas da camada de IA no banco do perfil.

Datas sempre com fuso; o SQLModel grava em UTC e devolve em UTC.
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def agora_utc() -> datetime:
    return datetime.now(UTC)


class ChamadaIA(SQLModel, table=True):
    """Uma linha por chamada, inclusive as servidas pelo cache e as que falharam.

    Nunca guarda o conteúdo enviado ou recebido: só metadados e custo.
    """

    __tablename__ = "chamadas_ia"

    id: int | None = Field(default=None, primary_key=True)
    criado_em: datetime = Field(default_factory=agora_utc, index=True)
    tarefa: str
    versao_prompt: int
    provedor: str
    modelo: str
    tokens_entrada: int = 0
    tokens_saida: int = 0
    custo_micro_usd: int | None = None  # None = preço desconhecido, nunca "zero"
    duracao_ms: int = 0
    cache_hit: bool = False
    sucesso: bool = True
    erro: str | None = None


class PedidoIA(SQLModel, table=True):
    """Pedido do modo manual: o pacote que a pessoa cola no chat dela.

    O pacote tem os dados enviados à IA; fica só no banco local do perfil, nunca em log.
    """

    __tablename__ = "pedidos_ia"

    id: str = Field(primary_key=True)  # "P-" + 6 caracteres
    criado_em: datetime = Field(default_factory=agora_utc, index=True)
    tarefa: str
    versao_prompt: int
    provedor: str
    modelo: str
    chave_cache: str = Field(index=True)
    pacote: str
    status: str = "pendente"  # pendente | respondido | cancelado
    tentativas: int = 0
    respondido_em: datetime | None = None


class CacheIA(SQLModel, table=True):
    __tablename__ = "cache_ia"

    chave: str = Field(primary_key=True)  # sha256 de tarefa, versão, modelo e entrada
    tarefa: str
    versao_prompt: int
    modelo: str
    saida_json: str
    criado_em: datetime = Field(default_factory=agora_utc)
