from pathlib import Path

import pytest
from pydantic import ValidationError

from app.vagas.nota import (
    CONFIG_PADRAO,
    ConfigAvaliacao,
    ErroConfigAvaliacao,
    Item,
    calcular_nota,
    carregar_config,
)

CONFIG = carregar_config()


def _itens(*pares, aplica=True) -> list[Item]:
    return [Item(peso=peso, decisao=decisao, aplica=aplica) for peso, decisao in pares]


def test_config_do_repositorio_tem_os_valores_do_plano():
    assert CONFIG.faixas == {"A": 85, "B": 70, "C": 55}
    assert CONFIG.corte == 60
    assert CONFIG.valores["atende"] == 1 and CONFIG.valores["nao_atende"] == 0


def test_tudo_atendido_e_100_faixa_a():
    nota = calcular_nota(_itens(("obrigatorio", "atende"), ("desejavel", "atende")), CONFIG)
    assert (nota.valor, nota.faixa, nota.recomenda) == (100, "A", True)


def test_soma_ponderada_pelo_peso():
    # obrigatório pesa 2 e desejável 1: (2*1 + 2*0,5 + 1*0) / 5 = 60
    itens = _itens(
        ("obrigatorio", "atende"), ("obrigatorio", "parcial"), ("desejavel", "nao_atende")
    )
    nota = calcular_nota(itens, CONFIG)
    assert (nota.valor, nota.faixa, nota.recomenda) == (60, "C", True)


def test_nao_sei_vale_um_pouco():
    nota = calcular_nota(_itens(("desejavel", "nao_sei")), CONFIG)
    assert nota.valor == 25


def test_obrigatorio_faltando_limita_a_nota():
    itens = _itens(*[("obrigatorio", "atende")] * 9, ("obrigatorio", "nao_atende"))
    nota = calcular_nota(itens, CONFIG)
    assert nota.valor == 69
    assert nota.faixa == "C"
    assert nota.obrigatorio_faltando


@pytest.mark.parametrize(
    ("valor", "faixa"), [(85, "A"), (84, "B"), (70, "B"), (69, "C"), (55, "C"), (54, "D"), (0, "D")]
)
def test_limites_das_faixas(valor, faixa):
    assert CONFIG.faixa(valor) == faixa


def test_abaixo_do_corte_nao_recomenda():
    nota = calcular_nota(_itens(("obrigatorio", "parcial"), ("desejavel", "nao_atende")), CONFIG)
    assert nota.valor == 33 and not nota.recomenda


def test_nao_se_aplica_sai_da_conta():
    itens = _itens(("obrigatorio", "atende")) + _itens(("obrigatorio", "nao_atende"), aplica=False)
    nota = calcular_nota(itens, CONFIG)
    assert nota.valor == 100 and not nota.obrigatorio_faltando


def test_sem_requisitos_nao_tem_nota():
    assert calcular_nota([], CONFIG) is None
    assert calcular_nota(_itens(("obrigatorio", "atende"), aplica=False), CONFIG) is None


def test_arredonda_para_o_inteiro_mais_proximo():
    # (1 + 0,5 + 0,5) / 3 = 66,67
    itens = _itens(("desejavel", "atende"), ("desejavel", "parcial"), ("desejavel", "parcial"))
    assert calcular_nota(itens, CONFIG).valor == 67


def test_config_invalida_da_erro_claro(tmp_path: Path):
    caminho = tmp_path / "avaliação.yaml"
    padrao = CONFIG_PADRAO.read_text(encoding="utf-8")
    caminho.write_text(padrao.replace("A: 85", "A: 50"), encoding="utf-8")
    with pytest.raises(ErroConfigAvaliacao, match="faixas"):
        carregar_config(caminho)


def test_config_e_imutavel():
    with pytest.raises(ValidationError):
        CONFIG.corte = 10  # type: ignore[misc]
    assert isinstance(CONFIG, ConfigAvaliacao)
