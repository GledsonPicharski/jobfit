"""Catálogo de tarefas de IA: nome, versão do prompt, nível de modelo e saída validada."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.dossie.modelos import Periodo, TipoFato, normalizar_tipo
from app.perfis.modelos import Nivel


@dataclass(frozen=True)
class Tarefa[S: BaseModel]:
    nome: str
    versao: int
    nivel: Nivel
    saida: type[S]


class RespostaTeste(BaseModel):
    ok: bool
    mensagem: str = Field(max_length=300)


TESTAR_CONEXAO = Tarefa(nome="testar_conexao", versao=1, nivel="barato", saida=RespostaTeste)


class EntradaExtracao(BaseModel):
    """O texto vai como campo JSON: é dado, não instrução (regra 8)."""

    fonte: Literal["texto", "cv", "descricoes_linkedin"]
    texto: str


class FatoExtraido(BaseModel):
    tipo: TipoFato
    texto: str = Field(min_length=1, max_length=600)
    empresa: str | None = Field(default=None, max_length=200)
    cargo: str | None = Field(default=None, max_length=200)
    periodo: Periodo | None = None
    metricas: dict[str, str | int | float] = Field(default_factory=dict)
    trecho: str = Field(min_length=1, max_length=1500)

    _tipo = field_validator("tipo", mode="before")(normalizar_tipo)


class FatosExtraidos(BaseModel):
    fatos: list[FatoExtraido] = Field(default_factory=list, max_length=300)


EXTRAIR_FATOS = Tarefa(nome="extrair_fatos", versao=1, nivel="barato", saida=FatosExtraidos)


class FatoParaAvaliar(BaseModel):
    id: str
    tipo: str
    texto: str
    empresa: str | None = None
    periodo: str | None = None


class EntradaAvaliacao(BaseModel):
    """A vaga vai como campo JSON: é dado não confiável (regra 8). Sem critérios privados."""

    vaga: str
    fatos: list[FatoParaAvaliar]


Categoria = Literal[
    "experiencia",
    "competencia",
    "ferramenta",
    "formacao",
    "idioma",
    "certificacao",
    "comportamental",
    "outro",
]


class RequisitoAvaliado(BaseModel):
    texto: str = Field(min_length=1, max_length=300)
    peso: Literal["obrigatorio", "desejavel"]
    categoria: Categoria = "outro"
    trecho: str = Field(min_length=1, max_length=800)
    decisao: Literal["atende", "parcial", "nao_sei", "nao_atende"]
    fatos: list[str] = Field(default_factory=list, max_length=12)
    justificativa: str = Field(default="", max_length=400)


class AvaliacaoVaga(BaseModel):
    titulo: str | None = Field(default=None, max_length=200)
    empresa: str | None = Field(default=None, max_length=200)
    requisitos: list[RequisitoAvaliado] = Field(default_factory=list, max_length=40)


AVALIAR_VAGA = Tarefa(nome="avaliar_vaga", versao=1, nivel="forte", saida=AvaliacaoVaga)

TAREFAS: dict[str, Tarefa] = {t.nome: t for t in [TESTAR_CONEXAO, EXTRAIR_FATOS, AVALIAR_VAGA]}


def texto_da_entrada(entrada: str | BaseModel) -> str:
    """Como a entrada vai para a IA, no modo API e no pacote do modo manual."""
    return entrada.model_dump_json(indent=2) if isinstance(entrada, BaseModel) else entrada
