"""O app só atende o próprio navegador: protege contra DNS rebinding e CSRF.

Servir em 127.0.0.1 não basta: qualquer site aberto no navegador consegue mandar
um POST para http://127.0.0.1:8765.
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from app.web.seguranca import ProtecaoLocal


@pytest.fixture
def cliente():
    app = FastAPI()
    app.add_middleware(ProtecaoLocal)

    @app.get("/")
    def ler():
        return PlainTextResponse("ok")

    @app.post("/")
    def gravar():
        return PlainTextResponse("gravado")

    return TestClient(app, base_url="http://127.0.0.1:8765")


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:8765", "127.0.0.1", "LOCALHOST"])
def test_hosts_locais_passam(cliente, host):
    assert cliente.get("/", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("host", ["evil.com", "evil.com:8765", "192.168.0.10:8765", ""])
def test_outros_hosts_sao_barrados(cliente, host):
    assert cliente.get("/", headers={"Host": host}).status_code == 400


def test_post_do_proprio_app_passa(cliente):
    resposta = cliente.post("/", headers={"Origin": "http://127.0.0.1:8765"})
    assert resposta.text == "gravado"


def test_post_com_referer_do_proprio_app_passa(cliente):
    resposta = cliente.post("/", headers={"Referer": "http://127.0.0.1:8765/p/ana/ia"})
    assert resposta.status_code == 200


@pytest.mark.parametrize(
    "cabecalhos",
    [
        {},
        {"Origin": "http://evil.com"},
        {"Origin": "null"},
        {"Origin": "http://127.0.0.1:9999"},
        {"Origin": "http://localhost:8765"},  # mesmo app, outra origem: o navegador separa
        {"Referer": "http://evil.com/pagina"},
    ],
)
def test_post_de_outra_origem_e_barrado(cliente, cabecalhos):
    assert cliente.post("/", headers=cabecalhos).status_code == 403


def test_cabecalhos_contra_iframe(cliente):
    resposta = cliente.get("/")
    assert resposta.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in resposta.headers["content-security-policy"]
    assert resposta.headers["x-content-type-options"] == "nosniff"
