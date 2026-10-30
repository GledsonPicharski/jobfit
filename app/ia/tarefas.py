"""Catálogo de tarefas de IA: nome, versão do prompt, nível de modelo e saída validada."""

from dataclasses import dataclass

from pydantic import BaseModel, Field

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

TAREFAS: dict[str, Tarefa] = {t.nome: t for t in [TESTAR_CONEXAO]}


def texto_da_entrada(entrada: str | BaseModel) -> str:
    """Como a entrada vai para a IA, no modo API e no pacote do modo manual."""
    return entrada.model_dump_json(indent=2) if isinstance(entrada, BaseModel) else entrada
