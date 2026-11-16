"""Filtros das buscas salvas: rodam em código, antes de qualquer IA."""

from decimal import Decimal

import pytest

from app.db import banco_do_perfil
from app.perfis.servico import criar_perfil
from app.vagas.buscas import (
    ErroBusca,
    FiltrosBusca,
    aceita_restricao,
    aplicar_busca,
    filtros_de,
    listar_buscas,
    obter_busca,
    salvar_busca,
    titulo_casa,
)
from app.vagas.metadados import Metadados, Salario


@pytest.fixture
def engine(pasta_dados):
    criar_perfil(pasta_dados, "Ana Exemplo", "ana")
    return banco_do_perfil("ana")


def test_titulo_casa_com_as_palavras_da_busca_em_qualquer_ordem():
    titulos = ["Gerente de Dados", "Head of Data"]
    assert titulo_casa("Gerente Sênior de Engenharia de Dados", titulos)
    assert titulo_casa("Head of Data & Analytics (Remote)", titulos)
    assert titulo_casa("Data Head of LATAM", titulos)
    assert not titulo_casa("Gerente de Produto", titulos)
    assert not titulo_casa("Analista de Dados", titulos)
    assert titulo_casa("Qualquer coisa", [])  # sem títulos: tudo passa


def test_restricao_de_pais_nas_vagas_remotas():
    assert aceita_restricao([], ["Brasil"])
    assert aceita_restricao(["Brazil"], ["Brasil"])
    assert aceita_restricao(["LATAM"], ["Brasil"])
    assert aceita_restricao(["Worldwide"], ["Brasil"])
    assert aceita_restricao(["United States", "Latin America"], ["Brasil"])
    assert not aceita_restricao(["United States", "Canada"], ["Brasil"])
    assert aceita_restricao(["Portugal"], ["Brasil", "Portugal"])
    assert aceita_restricao(["United States"], [])  # sem países na busca: não filtra


def _f(**campos) -> FiltrosBusca:
    return FiltrosBusca(**campos)


def test_so_remoto_barra_hibrido_e_presencial_mas_nao_o_desconhecido():
    f = _f(so_remoto=True)
    assert aplicar_busca(Metadados(modalidade="hibrido"), "", [], f).bloqueada
    assert not aplicar_busca(Metadados(modalidade="remoto"), "", [], f).bloqueada
    assert not aplicar_busca(Metadados(), "", [], f).bloqueada


def test_remota_so_para_outro_pais_e_barrada():
    f = _f(paises=["Brasil"])
    r = aplicar_busca(Metadados(modalidade="remoto"), "", ["United States"], f)
    assert r.bloqueios == ["Vaga remota só para United States."]


def test_empresa_setor_e_palavras():
    f = _f(
        empresas_excluidas=["Imobiliária Ação"],
        setores_excluidos=["mercado imobiliário"],
        palavras_obrigatorias=["python"],
        palavras_proibidas=["comissão"],
    )
    meta = Metadados(empresa="Imobiliaria Acao Ltda")
    texto = "Atuar no mercado imobiliário com Python. Ganhos por comissão."
    bloqueios = aplicar_busca(meta, texto, [], f).bloqueios
    assert bloqueios == [
        "Empresa excluída nesta busca: Imobiliária Ação.",
        "A vaga é de um setor que esta busca exclui: mercado imobiliário.",
        "A vaga menciona algo que esta busca evita: comissão.",
    ]
    falta = aplicar_busca(Metadados(), "Vaga com SQL", [], _f(palavras_obrigatorias=["python"]))
    assert falta.bloqueios == ["A descrição não menciona: python."]


def test_senioridade_e_salario():
    f = _f(senioridades=["gestao"], salario_minimo=20000)
    assert aplicar_busca(Metadados(senioridade="pleno"), "", [], f).bloqueios == [
        "Senioridade pleno; esta busca é de: gestão (coordenação, gerência, head)."
    ]
    baixo = Metadados(salario=Salario("BRL", Decimal(8000), Decimal(10000)))
    r = aplicar_busca(baixo, "", [], f)
    assert r.bloqueios == ["Salário informado (até 10.000 por mês) abaixo do mínimo desta busca."]
    assert "20" not in " ".join(r.bloqueios)  # o mínimo é privado
    dolar = Metadados(salario=Salario("USD", Decimal(3000), Decimal(4000)))
    assert not aplicar_busca(dolar, "", [], f).bloqueada


def test_buscas_no_banco(engine):
    busca = salvar_busca(
        engine,
        nome="Dados — remoto",
        titulos=["Gerente de Dados", "Head of Data"],
        so_remoto=True,
        paises=["Brasil"],
        palavras_proibidas=["comissão"],
    )
    assert [b.nome for b in listar_buscas(engine)] == ["Dados — remoto"]
    f = filtros_de(obter_busca(engine, busca.id))
    assert f.titulos == ["Gerente de Dados", "Head of Data"] and f.paises == ["Brasil"]

    salvar_busca(engine, busca_id=busca.id, nome="Dados", titulos=["Head of Data"])
    assert filtros_de(obter_busca(engine, busca.id)).titulos == ["Head of Data"]


def test_busca_valida(engine):
    with pytest.raises(ErroBusca, match="até 5 títulos"):
        salvar_busca(engine, nome="x", titulos=[f"t{i}" for i in range(6)])
    with pytest.raises(ErroBusca, match="pelo menos um título"):
        salvar_busca(engine, nome="x", titulos=["  "])
    with pytest.raises(ErroBusca, match="nome"):
        salvar_busca(engine, nome=" ", titulos=["Head of Data"])
