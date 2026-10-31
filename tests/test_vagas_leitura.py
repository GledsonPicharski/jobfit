import json
from pathlib import Path

import httpx2
import pytest

from app.vagas.leitura import ErroLeituraVaga, ler_texto, ler_url, normalizar_url

FIXTURES = Path(__file__).parent / "fixtures" / "vagas"


def _fixture(nome: str) -> str:
    return (FIXTURES / nome).read_text(encoding="utf-8")


def _cliente(rotas: dict[str, tuple[int, str]]) -> tuple[httpx2.Client, list[str]]:
    """Cliente com respostas gravadas; devolve também as URLs pedidas."""
    pedidas: list[str] = []

    def responder(pedido: httpx2.Request) -> httpx2.Response:
        url = str(pedido.url)
        pedidas.append(url)
        status, corpo = rotas.get(url, (404, "não encontrado"))
        return httpx2.Response(status, text=corpo)

    return httpx2.Client(transport=httpx2.MockTransport(responder)), pedidas


def test_greenhouse_pela_api_publica():
    api = "https://boards-api.greenhouse.io/v1/boards/empresaexemplo/jobs/4012345"
    cliente, pedidas = _cliente({api: (200, _fixture("greenhouse.json"))})
    vaga = ler_url("https://boards.greenhouse.io/empresaexemplo/jobs/4012345?gh_src=abc", cliente)

    assert pedidas == [api]
    assert vaga.fonte == "greenhouse"
    assert vaga.url == "https://boards.greenhouse.io/empresaexemplo/jobs/4012345"
    assert vaga.estruturado["titulo"] == "Senior Data Scientist"
    assert vaga.estruturado["empresa"] == "Empresa Exemplo"
    assert vaga.estruturado["local"] == "Remote - Brazil"
    assert "5+ years with Python and SQL" in vaga.texto
    assert "<li>" not in vaga.texto and "&lt;" not in vaga.texto


def test_greenhouse_no_endereco_novo():
    api = "https://boards-api.greenhouse.io/v1/boards/empresaexemplo/jobs/4012345"
    cliente, pedidas = _cliente({api: (200, _fixture("greenhouse.json"))})
    ler_url("https://job-boards.greenhouse.io/empresaexemplo/jobs/4012345", cliente)
    assert pedidas == [api]


def test_lever_pela_api_publica():
    api = "https://api.lever.co/v0/postings/fintech/a1b2c3d4-0000-4000-8000-000000000001"
    cliente, _ = _cliente({api: (200, _fixture("lever.json"))})
    vaga = ler_url("https://jobs.lever.co/fintech/a1b2c3d4-0000-4000-8000-000000000001", cliente)

    assert vaga.fonte == "lever"
    assert vaga.estruturado == {
        "titulo": "Analytics Manager",
        "local": "Curitiba, PR",
        "modalidade": "hibrido",
    }
    assert "Requisitos" in vaga.texto
    assert "SQL avançado" in vaga.texto
    assert "2 dias por semana" in vaga.texto


def test_pagina_com_json_ld_no_formato_da_gupy():
    url = "https://empresaexemplo.gupy.io/jobs/123456"
    cliente, _ = _cliente({url: (200, _fixture("gupy.html"))})
    vaga = ler_url(url, cliente)

    assert vaga.fonte == "gupy"
    assert vaga.estruturado["titulo"] == "Cientista de Dados Pleno"
    assert vaga.estruturado["empresa"] == "Empresa Exemplo"
    assert vaga.estruturado["local"] == "São Paulo, SP"
    assert "time de crédito — ação contínua" in vaga.texto
    assert "Menu do portal" not in vaga.texto


def test_pagina_sem_json_ld_usa_o_texto_principal():
    url = "https://carreiras.exemplo.test/vagas/ml-senior"
    cliente, _ = _cliente({url: (200, _fixture("pagina.html"))})
    vaga = ler_url(url, cliente)

    assert vaga.fonte == "pagina"
    assert vaga.texto.startswith("Engenheira de Machine Learning Sênior")
    assert "Docker e Kubernetes" in vaga.texto
    for fora in ("Cabeçalho do site", "Início · Vagas", "Rodapé", "var x", "color:red"):
        assert fora not in vaga.texto


def test_json_ld_remoto():
    pagina = _fixture("gupy.html").replace(
        '"@type": "JobPosting",', '"@type": "JobPosting", "jobLocationType": "TELECOMMUTE",'
    )
    url = "https://empresaexemplo.gupy.io/jobs/1"
    cliente, _ = _cliente({url: (200, pagina)})
    assert ler_url(url, cliente).estruturado["modalidade"] == "remoto"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/jobs/view/123",
        "https://br.linkedin.com/jobs/view/abc",
        "linkedin.com/jobs/view/1",
    ],
)
def test_linkedin_e_recusado_sem_buscar(url):
    cliente, pedidas = _cliente({})
    with pytest.raises(ErroLeituraVaga, match="cole o texto"):
        ler_url(url, cliente)
    assert pedidas == []


@pytest.mark.parametrize(
    "url", ["ftp://exemplo.test/vaga", "http://127.0.0.1:8765/p/ana", "http://localhost/x", "nada"]
)
def test_endereco_invalido_ou_local(url):
    cliente, pedidas = _cliente({})
    with pytest.raises(ErroLeituraVaga):
        ler_url(url, cliente)
    assert pedidas == []


def test_vaga_que_nao_existe_mais():
    cliente, _ = _cliente({})
    with pytest.raises(ErroLeituraVaga, match="encerrada"):
        ler_url("https://carreiras.exemplo.test/vagas/sumiu", cliente)


def test_pagina_sem_texto_suficiente():
    url = "https://carreiras.exemplo.test/vazia"
    cliente, _ = _cliente({url: (200, "<html><body><main>Carregando…</main></body></html>")})
    with pytest.raises(ErroLeituraVaga, match="cole o texto"):
        ler_url(url, cliente)


def test_texto_colado():
    vaga = ler_texto("  Cientista de Dados\r\n\r\n\r\n\r\nRequisitos: Python — ação  ")
    assert vaga.fonte == "texto"
    assert vaga.url is None
    assert vaga.texto == "Cientista de Dados\n\nRequisitos: Python — ação"


def test_texto_colado_vazio():
    with pytest.raises(ErroLeituraVaga, match="Cole"):
        ler_texto("   ")


@pytest.mark.parametrize(
    ("url", "normal"),
    [
        ("HTTPS://Exemplo.TEST/Vaga/1/?utm_source=x&id=7#topo", "https://exemplo.test/Vaga/1?id=7"),
        ("https://exemplo.test/vaga?gh_src=abc&ref=linkedin", "https://exemplo.test/vaga"),
    ],
)
def test_normalizar_url(url, normal):
    assert normalizar_url(url) == normal


def test_json_das_fixtures_e_valido():
    for nome in ("greenhouse.json", "lever.json"):
        json.loads(_fixture(nome))
