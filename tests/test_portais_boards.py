"""Leitores dos boards remotos, com respostas reais gravadas (recortadas) em 15/11/2026."""

from pathlib import Path
from urllib.parse import unquote

import httpx2
import pytest

from app.vagas.portais import Consulta, ErroPortal, getonboard, himalayas, remotive, weworkremotely

FIXTURES = Path(__file__).parent / "fixtures" / "portais"


def _cliente(rotas: dict[str, tuple[int, str]]) -> tuple[httpx2.Client, list[str]]:
    pedidas: list[str] = []

    def responder(pedido: httpx2.Request) -> httpx2.Response:
        url = unquote(str(pedido.url))
        pedidas.append(url)
        for prefixo, (status, corpo) in rotas.items():
            if url.startswith(prefixo):
                return httpx2.Response(status, text=corpo)
        return httpx2.Response(404, text="")

    return httpx2.Client(transport=httpx2.MockTransport(responder)), pedidas


def _fixture(nome: str) -> str:
    return (FIXTURES / nome).read_text(encoding="utf-8")


def test_remotive_uma_consulta_e_o_link_da_remotive():
    cliente, pedidas = _cliente(
        {"https://remotive.com/api/remote-jobs": (200, _fixture("remotive.json"))}
    )
    [vaga] = remotive.buscar(Consulta(titulos=["Office Assistant", "Gerente de Dados"]), cliente)
    assert pedidas == ["https://remotive.com/api/remote-jobs"]  # uma só, sem termo
    assert vaga.fonte == "remotive"
    assert vaga.url.startswith("https://remotive.com/remote-jobs/")  # link de volta (termos)
    assert vaga.estruturado["empresa"] == "Coalition Technologies"
    assert vaga.estruturado["modalidade"] == "remoto"
    assert vaga.estruturado["restricoes"] == ["Worldwide"]
    assert vaga.estruturado["publicada_em"].startswith("2026-11-11")
    assert "Salário:" in vaga.texto and "<p>" not in vaga.texto


def test_we_work_remotely_separa_empresa_e_cargo():
    cliente, _ = _cliente({weworkremotely.FEED: (200, _fixture("weworkremotely.rss"))})
    vagas = weworkremotely.buscar(Consulta(titulos=["Account Executive", "Sales"]), cliente)
    assert [(v.estruturado["empresa"], v.estruturado["titulo"]) for v in vagas] == [
        ("Roofr", "Sales Development Representative"),
        ("ServiceNow", "Senior CRM Account Executive"),
    ]
    roofr = vagas[0]
    assert (
        roofr.url == "https://weworkremotely.com/remote-jobs/roofr-sales-development-representative"
    )
    assert roofr.estruturado["restricoes"] == ["Anywhere in the World", "Canada"]
    assert roofr.estruturado["publicada_em"]


def test_we_work_remotely_feed_quebrado_e_erro_do_portal():
    cliente, _ = _cliente({weworkremotely.FEED: (200, "<html>manutenção</rss")})
    with pytest.raises(ErroPortal):
        weworkremotely.buscar(Consulta(titulos=["Sales"]), cliente)


def test_himalayas_busca_por_titulo_e_traz_paises_aceitos():
    cliente, pedidas = _cliente(
        {"https://himalayas.app/jobs/api/search": (200, _fixture("himalayas.json"))}
    )
    vagas = himalayas.buscar(Consulta(titulos=["Data Manager"]), cliente)
    assert pedidas == ["https://himalayas.app/jobs/api/search?q=Data Manager&limit=20"]
    assert len(vagas) == 3
    lifelancer = vagas[0]
    assert lifelancer.fonte == "himalayas"
    assert lifelancer.url.startswith("https://himalayas.app/companies/lifelancer/jobs/")
    assert "utm_source" not in lifelancer.url
    assert lifelancer.estruturado["restricoes"] == ["United States"]
    assert lifelancer.estruturado["publicada_em"].startswith("2026-")


def test_local_com_paises_demais_e_encurtado():
    from app.vagas.portais import montar

    paises = ", ".join(f"País {i}" for i in range(60))
    vaga = montar("texto", "himalayas", "https://x", titulo="T", empresa="E", local=paises)
    assert len(vaga.estruturado["local"]) <= 80 and vaga.estruturado["local"].endswith("…")


def test_get_on_board_modalidade_e_empresa():
    cliente, _ = _cliente(
        {"https://www.getonbrd.com/api/v0/search/jobs": (200, _fixture("getonboard.json"))}
    )
    vagas = getonboard.buscar(Consulta(titulos=["Manager"]), cliente)
    por_titulo = {v.estruturado["titulo"]: v for v in vagas}
    presencial = por_titulo["Project Manager Telecommunications"]
    assert presencial.estruturado["modalidade"] == "presencial"
    assert presencial.estruturado["empresa"] == "Niuro"
    assert "restricoes" not in presencial.estruturado
    remota = por_titulo["Partnerships and Campaign Manager"]
    assert remota.estruturado["modalidade"] == "remoto"
    assert remota.estruturado["restricoes"] == ["Remote"]
    assert remota.url == (
        "https://www.getonbrd.com/jobs/partnerships-and-campaign-manager-remote-adfuel-remote"
    )


def test_ainda_aberta_dos_boards():
    url = "https://www.getonbrd.com/jobs/partnerships-and-campaign-manager-remote-adfuel-remote"
    assert getonboard.ainda_aberta(url, _cliente({url: (301, "")})[0])  # vai para a categoria
    assert not getonboard.ainda_aberta(url, _cliente({})[0])
    vaga_hima = "https://himalayas.app/companies/x/jobs/y"
    assert himalayas.ainda_aberta(vaga_hima, _cliente({vaga_hima: (403, "bloqueado")})[0])
    assert not himalayas.ainda_aberta(vaga_hima, _cliente({})[0])
    vaga = "https://remotive.com/remote-jobs/marketing/remote-office-assistant-1680495"
    assert remotive.ainda_aberta(vaga, _cliente({vaga: (200, "ok")})[0])
    assert not remotive.ainda_aberta(vaga, _cliente({})[0])
