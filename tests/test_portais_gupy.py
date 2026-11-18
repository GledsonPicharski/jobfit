"""Leitor da Gupy, com a resposta real da busca gravada (recortada) em 15/11/2026."""

from pathlib import Path
from urllib.parse import unquote

import httpx2
import pytest

from app.vagas.portais import Consulta, ErroPortal, gupy

FIXTURES = Path(__file__).parent / "fixtures" / "portais"


def _cliente(rotas: dict[str, tuple[int, str, dict]]) -> tuple[httpx2.Client, list[str]]:
    pedidas: list[str] = []

    def responder(pedido: httpx2.Request) -> httpx2.Response:
        url = unquote(str(pedido.url))
        pedidas.append(url)
        for prefixo, (status, corpo, cabecalhos) in rotas.items():
            if url.startswith(prefixo):
                return httpx2.Response(status, text=corpo, headers=cabecalhos)
        return httpx2.Response(404, text="")

    return httpx2.Client(transport=httpx2.MockTransport(responder)), pedidas


def test_gupy_busca_por_titulo_com_link_limpo():
    corpo = (FIXTURES / "gupy.json").read_text(encoding="utf-8")
    cliente, pedidas = _cliente({gupy.API: (200, corpo, {})})
    vagas = gupy.buscar(Consulta(titulos=["Gerente de Dados"]), cliente)

    assert pedidas == [f"{gupy.API}?jobName=Gerente de Dados&limit=20&offset=0"]
    primeira = vagas[0]
    assert primeira.fonte == "gupy"
    assert primeira.url == "https://vissimo.gupy.io/jobs/12890009"  # sem o rastreio
    assert primeira.estruturado["empresa"] == "Víssimo"
    assert primeira.estruturado["modalidade"] == "hibrido"
    assert primeira.estruturado["local"] == "São Paulo - São Paulo"
    assert primeira.estruturado["publicada_em"].startswith("2026-11-13")
    assert "Contratação: PJ" in primeira.texto
    assert all(
        "Gerente" in v.estruturado["titulo"] or "GERENTE" in v.estruturado["titulo"] for v in vagas
    )


def test_gupy_formato_novo_vira_erro_do_portal():
    cliente, _ = _cliente({gupy.API: (200, "<html>nova versão</html>", {})})
    with pytest.raises(ErroPortal):
        gupy.buscar(Consulta(titulos=["Gerente de Dados"]), cliente)


def test_gupy_ainda_aberta():
    url = "https://vissimo.gupy.io/jobs/12890009"
    aberta, _ = _cliente(
        {url: (200, '<script type="application/ld+json">{"@type":"JobPosting"}', {})}
    )
    assert gupy.ainda_aberta(url, aberta)
    login, _ = _cliente({url: (307, "", {"location": "/candidates/signin"})})
    assert not gupy.ainda_aberta(url, login)
    assert not gupy.ainda_aberta(url, _cliente({})[0])
