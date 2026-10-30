import pytest

from app.ia.prompts import PromptAusente, carregar_prompt
from app.ia.tarefas import TAREFAS


@pytest.mark.parametrize("tarefa", TAREFAS.values(), ids=lambda t: t.nome)
def test_toda_tarefa_tem_prompt_da_versao_declarada(tarefa):
    assert carregar_prompt(tarefa.nome, tarefa.versao).strip()


def test_prompt_ausente_da_erro_claro():
    with pytest.raises(PromptAusente, match=r"nao_existe\.v7\.md"):
        carregar_prompt("nao_existe", 7)


def test_nomes_de_tarefa_unicos():
    assert all(nome == t.nome for nome, t in TAREFAS.items())
