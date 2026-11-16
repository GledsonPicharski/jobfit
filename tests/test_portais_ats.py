"""Leitores dos ATS por empresa, com respostas reais gravadas (recortadas) em 15/11/2026."""

import json
from pathlib import Path

import httpx2

from app.vagas.catalogo import Empresa
from app.vagas.portais import Consulta, ashby, greenhouse, lever

FIXTURES = Path(__file__).parent / "fixtures" / "portais"


def _fixture(nome: str) -> str:
    return (FIXTURES / nome).read_text(encoding="utf-8")


def _cliente(rotas: dict[str, tuple[int, str]]) -> tuple[httpx2.Client, list[str]]:
    pedidas: list[str] = []

    def responder(pedido: httpx2.Request) -> httpx2.Response:
        url = str(pedido.url)
        pedidas.append(url)
        status, corpo = rotas.get(url, (404, "{}"))
        return httpx2.Response(status, text=corpo, headers={"content-type": "application/json"})

    return httpx2.Client(transport=httpx2.MockTransport(responder)), pedidas


VTEX = Empresa(nome="VTEX", ats="greenhouse", quadro="vtex")
YUNO = Empresa(nome="Yuno", ats="lever", quadro="yuno")
NUBANK = Empresa(nome="Nubank", ats="ashby", quadro="nubank")
GH_LISTA = "https://boards-api.greenhouse.io/v1/boards/vtex/jobs"
GH_VAGA = "https://boards-api.greenhouse.io/v1/boards/vtex/jobs/6100504004"


def test_greenhouse_le_o_texto_so_das_vagas_que_passam_no_titulo():
    cliente, pedidas = _cliente(
        {
            GH_LISTA: (200, _fixture("greenhouse_lista.json")),
            GH_VAGA: (200, _fixture("greenhouse_vaga.json")),
        }
    )
    consulta = Consulta(titulos=["Analista Administrativo"], empresas=[VTEX, YUNO])
    vagas = greenhouse.buscar(consulta, cliente)

    assert pedidas == [GH_LISTA, GH_VAGA]  # a lista e um detalhe; Yuno não é do Greenhouse
    [vaga] = vagas
    assert vaga.fonte == "greenhouse"
    assert vaga.url == "https://job-boards.greenhouse.io/vtex/jobs/6100504004"
    assert vaga.estruturado["empresa"] == "VTEX"
    assert vaga.estruturado["titulo"].startswith("Analista Administrativo Tech")
    assert vaga.estruturado["publicada_em"].startswith("2026-08-05")
    assert "SOBRE A VAGA" in vaga.texto and "<p" not in vaga.texto


def test_erro_numa_empresa_vira_aviso_e_nao_para_as_outras():
    outra = Empresa(nome="Empresa Fora do Ar", ats="greenhouse", quadro="fora")
    cliente, _ = _cliente(
        {
            "https://boards-api.greenhouse.io/v1/boards/fora/jobs": (503, "erro"),
            GH_LISTA: (200, _fixture("greenhouse_lista.json")),
            GH_VAGA: (200, _fixture("greenhouse_vaga.json")),
        }
    )
    consulta = Consulta(titulos=["Analista Administrativo"], empresas=[outra, VTEX])
    assert len(greenhouse.buscar(consulta, cliente)) == 1
    assert consulta.avisos == ["Empresa Fora do Ar: respondeu com erro 503"]


def test_greenhouse_ainda_aberta():
    url = "https://job-boards.greenhouse.io/vtex/jobs/6100504004"
    cliente, _ = _cliente({GH_VAGA: (200, _fixture("greenhouse_vaga.json"))})
    assert greenhouse.ainda_aberta(url, cliente)
    fechada, _ = _cliente({})
    assert not greenhouse.ainda_aberta(url, fechada)
    assert greenhouse.ainda_aberta("https://empresa.com/vagas?gh_jid=1", fechada)  # sem como saber


def test_lever_traz_texto_modalidade_e_paises_da_vaga_remota():
    cliente, pedidas = _cliente(
        {"https://api.lever.co/v0/postings/yuno?mode=json": (200, _fixture("lever.json"))}
    )
    consulta = Consulta(titulos=["Engineering Manager"], empresas=[YUNO, VTEX])
    [vaga] = lever.buscar(consulta, cliente)

    assert pedidas == ["https://api.lever.co/v0/postings/yuno?mode=json"]
    assert vaga.fonte == "lever"
    assert vaga.url.startswith("https://jobs.lever.co/yuno/016fc224")
    assert vaga.estruturado["modalidade"] == "remoto"
    assert vaga.estruturado["empresa"] == "Yuno"
    assert "Brazil" in vaga.estruturado["restricoes"]
    assert vaga.estruturado["publicada_em"].startswith("2026-02")
    assert vaga.texto.startswith("Engineering Manager - Core Payments")


def test_lever_ainda_aberta():
    url = "https://jobs.lever.co/yuno/016fc224-be91-48f3-8075-3ca86b614b4f"
    api = "https://api.lever.co/v0/postings/yuno/016fc224-be91-48f3-8075-3ca86b614b4f"
    aberta, _ = _cliente({api: (200, "{}")})
    assert lever.ainda_aberta(url, aberta)
    assert not lever.ainda_aberta(url, _cliente({})[0])


ASHBY = "https://api.ashbyhq.com/posting-api/job-board/nubank?includeCompensation=true"


def test_ashby_traz_modalidade_local_e_data():
    cliente, _ = _cliente({ASHBY: (200, _fixture("ashby.json"))})
    consulta = Consulta(titulos=["Software Engineer", "Head of Risk"], empresas=[NUBANK])
    vagas = ashby.buscar(consulta, cliente)

    assert [v.estruturado["titulo"] for v in vagas] == [
        "Senior Software Engineer - BR",
        "Head of Risk US",
    ]
    engenharia = vagas[0]
    assert engenharia.fonte == "ashby"
    assert engenharia.url == "https://jobs.ashbyhq.com/nubank/20ae8a5c-6692-41f1-8567-a0446a3a5983"
    assert engenharia.estruturado["modalidade"] == "hibrido"
    assert engenharia.estruturado["local"] == "São Paulo"
    assert engenharia.estruturado["publicada_em"].startswith("2026-07-19")
    assert "restricoes" not in engenharia.estruturado  # só vagas remotas têm restrição


def test_ashby_ainda_aberta_pela_lista():
    cliente, _ = _cliente({ASHBY: (200, _fixture("ashby.json"))})
    aberta = "https://jobs.ashbyhq.com/nubank/20ae8a5c-6692-41f1-8567-a0446a3a5983"
    fechada = "https://jobs.ashbyhq.com/nubank/00000000-0000-0000-0000-000000000000"
    assert ashby.ainda_aberta(aberta, cliente)
    assert not ashby.ainda_aberta(fechada, cliente)


def test_fixtures_sao_json_valido_e_sem_e_mail():
    for arquivo in FIXTURES.glob("*.json"):
        json.loads(arquivo.read_text(encoding="utf-8"))
        assert "@" not in arquivo.read_text(encoding="utf-8"), arquivo.name
