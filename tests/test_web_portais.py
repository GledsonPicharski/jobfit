"""Tela de Portais e o resumo do scan no Início."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import banco_do_perfil
from app.main import create_app
from app.perfis.servico import criar_perfil
from app.vagas.catalogo import carregar_catalogo
from app.vagas.portais import ErroPortal
from app.vagas.scanner import portais_do_perfil
from app.vagas.tabelas import Vaga, Varredura
from app.web import rotas_scanner

ORIGEM = "http://127.0.0.1:8765"


@pytest.fixture
def cliente():
    return TestClient(create_app(), base_url=ORIGEM, headers={"Origin": ORIGEM})


@pytest.fixture
def ana(pasta_dados):
    return criar_perfil(pasta_dados, "Ana Exemplo", "ana")


def test_tela_mostra_lidos_lembretes_e_descartados(cliente, ana):
    tela = cliente.get("/p/ana/portais").text
    assert "Lidos pelo scan" in tela and "Greenhouse" in tela and "Remotive" in tela
    assert "Para checar à mão" in tela and "Wellfound" in tela
    assert "Remote OK" in tela and "Redundante" in tela
    assert "Nubank" in tela  # empresas acompanhadas


def test_desligar_e_ligar_portal(cliente, ana):
    cliente.post("/p/ana/portais/remotive/ligar")
    assert portais_do_perfil(banco_do_perfil("ana"))["remotive"].desligado
    cliente.post("/p/ana/portais/remotive/ligar", data={"ligado": "true"})
    assert not portais_do_perfil(banco_do_perfil("ana"))["remotive"].desligado


def test_acrescentar_empresa_confere_o_quadro(cliente, ana, pasta_dados, monkeypatch):
    conferidos = []

    def conferir(ats, quadro, _cliente):
        conferidos.append((ats, quadro))
        if quadro == "inexistente":
            raise ErroPortal("não achei o quadro 'inexistente' no Lever")
        return 12

    monkeypatch.setattr(rotas_scanner, "conferir_quadro", conferir)
    resposta = cliente.post(
        "/p/ana/portais/empresas",
        data={"nome": "Empresa Ção", "quadro": "https://jobs.lever.co/empresa-cao"},
    )
    assert "Empresa Ção acrescentada: o quadro tem 12 vaga(s) agora." in resposta.text
    assert conferidos == [("lever", "empresa-cao")]
    assert any(e.quadro == "empresa-cao" for e in carregar_catalogo(pasta_dados).empresas)

    erro = cliente.post(
        "/p/ana/portais/empresas", data={"nome": "X", "quadro": "inexistente", "ats": "lever"}
    )
    assert erro.status_code == 400 and "não achei o quadro" in erro.text
    sem_ats = cliente.post("/p/ana/portais/empresas", data={"nome": "X", "quadro": "abc"})
    assert sem_ats.status_code == 400 and "Escolha o sistema" in sem_ats.text


def test_lembrete_novo_portal_e_inicio(cliente, ana, pasta_dados):
    cliente.post(
        "/p/ana/portais/novo",
        data={"nome": "Portal Só Meu", "url": "https://exemplo.com.br", "frequencia_dias": "3"},
    )
    cliente.post("/p/ana/portais/wellfound/lembrete", data={"frequencia_dias": "7"})
    inicio = cliente.get("/p/ana").text
    assert "Hora de checar" in inicio and "Portal Só Meu" in inicio and "Wellfound" in inicio

    resposta = cliente.post(
        "/p/ana/portais/wellfound/checado", data={"voltar": "inicio"}, follow_redirects=False
    )
    assert resposta.headers["location"] == "/p/ana"
    inicio = cliente.get("/p/ana").text
    assert "Portal Só Meu" in inicio and "Wellfound" not in inicio


def test_inicio_mostra_vagas_novas_e_ultimo_scan(cliente, ana):
    engine = banco_do_perfil("ana")
    with Session(engine) as sessao:
        sessao.add(Vaga(fonte="gupy", titulo="Gerente de Dados", texto="x", hash_texto="a",
                        estado="nova", prenota=70))  # fmt: skip
        sessao.add(Vaga(fonte="gupy", titulo="Estagiário", texto="y", hash_texto="b",
                        estado="nova", prenota=5))  # fmt: skip
        sessao.add(Varredura(inicio=datetime(2026, 11, 16, 8, tzinfo=UTC), estado="concluida"))
        sessao.commit()
    inicio = cliente.get("/p/ana").text
    assert "1 vaga(s) nova(s)" in inicio and "pré-nota 70" in inicio
    assert "Estagiário" not in inicio
    assert "Último scan" in inicio


def test_portais_sem_nada_no_banco_nao_quebra(cliente, ana):
    assert cliente.get("/p/ana/portais").status_code == 200
