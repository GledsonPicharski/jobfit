"""Prompts versionados em `prompts/<tarefa>.v<N>.md`.

A versão vem da tarefa, nunca do "arquivo mais novo": mudar o texto exige criar
`v<N+1>` e subir a versão em `tarefas.py`, o que invalida o cache e pede evals.
"""

from pathlib import Path

from app.arquivos import ler_texto

PASTA_PROMPTS = Path(__file__).resolve().parents[2] / "prompts"


class PromptAusente(FileNotFoundError):
    pass


def carregar_prompt(nome: str, versao: int) -> str:
    caminho = PASTA_PROMPTS / f"{nome}.v{versao}.md"
    if not caminho.is_file():
        raise PromptAusente(f"Prompt {caminho.name} não encontrado em {PASTA_PROMPTS}.")
    return ler_texto(caminho)
