"""Telas das buscas salvas, do scan e das vagas novas."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db import banco_do_perfil
from app.dossie.versoes import caminho_dossie
from app.main import create_app
from app.perfis.servico import criar_perfil
from app.vagas import scanner
from app.vagas.buscas import listar_buscas, salvar_busca
from app.vagas.tabelas import Vaga, VagaOrigem

ORIGEM = "http://127.0.0.1:8765"
RAIZ = Path(__file__).resolve().parents[1]
EXEMPLO = (RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md").read_text(encoding="utf-8")


@pytest.fixture
def cliente():
    return TestClient(create_app(), base_url=ORIGEM, headers={"Origin": ORIGEM})


@pytest.fixture
def ana(pasta_dados):
    perfil = criar_perfil(pasta_dados, "Ana Exemplo", "ana")
    caminho_dossie(pasta_dados, "ana").write_text(EXEMPLO, encoding="utf-8")
    return perfil


def _nova(engine, titulo, prenota, portal="greenhouse", **campos) -> int:
    with Session(engine) as sessao:
        campos = {"aberta": True} | campos
        vaga = Vaga(
            fonte=portal, titulo=titulo, empresa="Empresa Ção", texto=f"{titulo} texto",
            hash_texto=titulo, estado="nova", prenota=prenota, **campos,
        )  # fmt: skip
        sessao.add(vaga)
        sessao.flush()
        sessao.add(VagaOrigem(vaga_id=vaga.id, portal=portal, url=f"https://x/{vaga.id}"))
        sessao.commit()
        return vaga.id


def test_criar_editar_e_apagar_busca(cliente, ana):
    tela = cliente.get("/p/ana/buscas").text
    assert "Nenhuma busca ainda" in tela and "Rodar agora" in tela

    resposta = cliente.post(
        "/p/ana/buscas",
        data={
            "nome": "Dados — remoto",
            "titulos": "Gerente de Dados\nHead of Data, Analytics",
            "paises": "Brasil",
            "so_remoto": "true",
            "ativa": "true",
            "salario_minimo": "R" + "$ 25.000",  # montado: o pre-commit barra o literal
            "portais": ["greenhouse", "gupy"],
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    [busca] = listar_buscas(banco_do_perfil("ana"))
    assert busca.salario_minimo == 25000
    tela = cliente.get("/p/ana/buscas").text
    assert "Dados — remoto" in tela and "Head of Data, Analytics" in tela  # vírgula no título
    assert "2 portal(is)" in tela

    editar = cliente.get(f"/p/ana/buscas/{busca.id}").text
    assert "Gerente de Dados" in editar and "25000" in editar

    erro = cliente.post(
        f"/p/ana/buscas/{busca.id}",
        data={"nome": "Dados", "titulos": "\n".join(f"Título {i}" for i in range(6))},
    )
    assert erro.status_code == 400 and "até 5 títulos" in erro.text
    assert "Título 5" in erro.text  # o que a pessoa digitou não se perde

    cliente.post(f"/p/ana/buscas/{busca.id}/excluir")
    assert listar_buscas(banco_do_perfil("ana")) == []


def test_rodar_sem_busca_avisa(cliente, ana):
    resposta = cliente.post("/p/ana/scan")
    assert resposta.status_code == 400 and "Crie uma busca" in resposta.text


def test_rodar_agora_inicia_em_segundo_plano(cliente, ana, monkeypatch):
    engine = banco_do_perfil("ana")
    salvar_busca(engine, nome="Dados", titulos=["Head of Data"])
    chamadas = []
    monkeypatch.setattr(scanner, "varrer", lambda *a, **k: chamadas.append(k["origem"]))

    resposta = cliente.post("/p/ana/scan", follow_redirects=False)
    assert resposta.headers["location"] == "/p/ana/buscas"
    for _ in range(50):
        if chamadas and not scanner._rodando:
            break
        time.sleep(0.05)
    assert chamadas == ["tela"]


def test_scan_rodando_nao_inicia_outro_e_a_tela_se_atualiza(cliente, ana):
    from app.vagas.tabelas import Varredura

    engine = banco_do_perfil("ana")
    with Session(engine) as sessao:
        sessao.add(Varredura(origem="tela", estado="rodando"))
        sessao.commit()
    assert scanner.iniciar(ana, engine, Path(".")) is False
    estado = cliente.get("/p/ana/scan/estado").text
    assert 'hx-trigger="every 3s"' in estado and "Buscando vagas" in estado


def test_vagas_novas_ordenadas_pela_prenota(cliente, ana):
    engine = banco_do_perfil("ana")
    _nova(engine, "Gerente de Dados", 40)
    _nova(engine, "Head of Data", 80, portal="remotive")
    _nova(engine, "Analista Júnior", 10)

    tela = cliente.get("/p/ana/vagas").text
    assert tela.index("Head of Data") < tela.index("Gerente de Dados")
    assert "Analista Júnior" not in tela  # abaixo da pré-nota mínima
    assert "1 vaga(s) nova(s) com pré-nota abaixo de 30" in tela
    assert "Remotive" in tela and "Greenhouse" in tela

    todas = cliente.get("/p/ana/vagas?todas=1").text
    assert "Analista Júnior" in todas
    so_remotive = cliente.get("/p/ana/vagas?portal=remotive").text
    assert "Head of Data" in so_remotive and "Gerente de Dados" not in so_remotive


def test_descartar_da_lista_volta_para_a_lista(cliente, ana):
    engine = banco_do_perfil("ana")
    vaga_id = _nova(engine, "Head of Data", 80)
    resposta = cliente.post(
        f"/p/ana/vagas/{vaga_id}/estado",
        data={"estado": "descartada", "voltar": "lista"},
        follow_redirects=False,
    )
    assert resposta.headers["location"] == "/p/ana/vagas#novas"
    tela = cliente.get("/p/ana/vagas").text
    assert 'id="novas"' not in tela  # saiu das novas
    assert "Descartada" in tela  # e ficou na lista, como descartada


def test_pagina_da_vaga_mostra_origem_e_encerrada(cliente, ana):
    from datetime import UTC, datetime

    engine = banco_do_perfil("ana")
    vaga_id = _nova(
        engine, "Head of Data", 80, aberta=False, encerrada_em=datetime(2026, 11, 20, tzinfo=UTC)
    )
    tela = cliente.get(f"/p/ana/vagas/{vaga_id}").text
    assert "Vista em:" in tela and "Greenhouse" in tela
    assert "Esta vaga foi encerrada no portal" in tela
    assert "pré-nota 80" in tela
    assert ">Nova<" not in tela  # "nova" não é um botão de estado


def test_menu_tem_buscas_e_portais(cliente, ana):
    tela = cliente.get("/p/ana").text
    assert "/p/ana/buscas" in tela and "/p/ana/portais" in tela
