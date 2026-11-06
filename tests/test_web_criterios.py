from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.perfis.servico import carregar_perfil, criar_perfil

ORIGEM = "http://127.0.0.1:8765"


@pytest.fixture
def cliente():
    return TestClient(create_app(), base_url=ORIGEM, headers={"Origin": ORIGEM})


@pytest.fixture
def ana(pasta_dados):
    return criar_perfil(pasta_dados, "Ana Exemplo", "ana")


def test_criterios_no_menu_e_padrao_aceita_tudo(cliente, ana):
    tela = cliente.get("/p/ana/criterios").text
    assert 'href="/p/ana/criterios"' in tela
    assert tela.count('name="modalidades"') == 3
    assert tela.count("checked") == 3  # as três modalidades


def test_salvar_criterios(cliente, ana, pasta_dados):
    resposta = cliente.post(
        "/p/ana/criterios",
        data={
            "modalidades": ["remoto", "hibrido"],
            "senioridades": ["senior", "gestao"],
            "cidades": "Curitiba\nSão José dos Pinhais, Curitiba",
            "salario_minimo": "15.000",
            "palavras_evitar": "mercado imobiliário\n\n",
        },
        follow_redirects=False,
    )
    assert resposta.headers["location"] == "/p/ana/criterios?salvo=1"
    c = carregar_perfil(pasta_dados, "ana").criterios
    assert c.modalidades == ["remoto", "hibrido"]
    assert c.cidades == ["Curitiba", "São José dos Pinhais"]
    assert c.salario_minimo == Decimal(15000)
    assert c.palavras_evitar == ["mercado imobiliário"]
    tela = cliente.get("/p/ana/criterios?salvo=1").text
    assert 'value="15000"' in tela and "Critérios salvos." in tela


@pytest.mark.parametrize(
    ("dados", "erro"),
    [
        ({"salario_minimo": "muito"}, "Valor inválido"),
        ({"modalidades": ["remoto"], "salario_minimo": "-5"}, "salario_minimo"),
        ({}, "Marque ao menos uma modalidade."),
    ],
)
def test_criterios_invalidos(cliente, ana, pasta_dados, dados, erro):
    resposta = cliente.post("/p/ana/criterios", data={"modalidades": ["remoto"], **dados})
    if not dados:
        resposta = cliente.post("/p/ana/criterios", data={})
    assert resposta.status_code == 400
    assert erro in resposta.text
    assert carregar_perfil(pasta_dados, "ana").criterios.salario_minimo is None
