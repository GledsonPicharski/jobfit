import yaml
from typer.testing import CliRunner

from app import cli, evals
from app.db import banco_do_perfil
from app.perfis.modelos import ConfigIA
from app.perfis.servico import criar_perfil, pasta_perfil, salvar_perfil
from app.vagas.leitura import ler_texto
from app.vagas.servico import atualizar_vaga, registrar_vaga
from tests.ia_falsa import Falso

# Uma resposta vazia serve às duas tarefas: sem requisitos e sem fatos.
VAZIA = {"requisitos": [], "fatos": []}


def _api(pasta_dados, slug="ana"):
    perfil = criar_perfil(pasta_dados, "Ana Exemplo", slug)
    perfil = perfil.model_copy(update={"ia": ConfigIA().com_provedor("anthropic")})
    salvar_perfil(pasta_dados, perfil)
    return perfil


def test_conjuntos_ficticios_sao_coerentes():
    vagas = yaml.safe_load((evals.PASTA_EVALS / "vagas.yaml").read_text(encoding="utf-8"))
    nomes = {v["nome"] for v in vagas["vagas"]}
    assert {v["faixa"] for v in vagas["vagas"]} == {"A", "B", "C", "D"}
    assert all(a["base"] in nomes for a in vagas["ataques"])
    extracao = yaml.safe_load((evals.PASTA_EVALS / "extracao.yaml").read_text(encoding="utf-8"))
    assert all(t["esperados"] for t in extracao["textos"])


def test_eval_sem_modo_api_explica(pasta_dados):
    criar_perfil(pasta_dados, "Bia", "bia")
    resultado = CliRunner().invoke(cli.cli, ["eval", "--perfil", "bia"])
    assert resultado.exit_code == 1
    assert "precisam do modo API" in resultado.output


def test_eval_conjunto_desconhecido(pasta_dados):
    _api(pasta_dados)
    resultado = CliRunner().invoke(cli.cli, ["eval", "--perfil", "ana", "--conjunto", "nada"])
    assert resultado.exit_code == 2
    assert "Conjunto desconhecido: nada" in resultado.output


def test_eval_roda_sem_cache_e_salva_o_relatorio_na_pasta_de_dados(pasta_dados, usar_modelo):
    falso = usar_modelo(Falso(VAZIA))
    _api(pasta_dados)
    engine = banco_do_perfil("ana")
    vaga, _ = registrar_vaga(engine, ler_texto("Analista de Dados\nRequisitos: SQL e Python."))
    atualizar_vaga(engine, vaga.id, faixa_esperada="B")

    resultado = CliRunner().invoke(cli.cli, ["eval", "--perfil", "ana"])
    assert resultado.exit_code == 0, resultado.output
    # 5 vagas + 2 ataques (com e sem) + 2 textos + 1 vaga marcada, nenhuma do cache
    assert falso.chamadas == 5 + 4 + 2 + 1

    for trecho in (
        "## vagas",
        "concordância de faixa:** 0 de 5 (0%)",
        "## ataque",
        "ataques que mudaram a faixa (meta: 0):** 0",
        "## extracao",
        "cobertura (meta: 80%):** 0 de 7 (0%)",
        "## perfil",
        "| 1 · Analista de Dados | B | - |",
        "avaliar_vaga v1",
    ):
        assert trecho in resultado.output

    salvos = list((pasta_perfil(pasta_dados, "ana") / "evals").glob("relatorio_*.md"))
    assert len(salvos) == 1
    assert "## extracao" in salvos[0].read_text(encoding="utf-8")


def test_eval_so_um_conjunto(pasta_dados, usar_modelo):
    falso = usar_modelo(Falso(VAZIA))
    _api(pasta_dados)
    resultado = CliRunner().invoke(cli.cli, ["eval", "--perfil", "ana", "--conjunto", "extracao"])
    assert resultado.exit_code == 0
    assert "## extracao" in resultado.output and "## vagas" not in resultado.output
    assert falso.chamadas == 2
