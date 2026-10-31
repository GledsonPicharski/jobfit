import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.db import banco_do_perfil
from app.dossie.formato import ler_dossie
from app.dossie.versoes import caminho_dossie
from app.ia.erros import ErroIA
from app.main import create_app
from app.perfis.modelos import ConfigIA, Criterios
from app.perfis.servico import carregar_perfil, criar_perfil, salvar_perfil
from app.vagas import leitura, servico
from tests.ia_falsa import Falso
from tests.test_vagas_servico import SAIDA, VAGA

ORIGEM = "http://127.0.0.1:8765"
RAIZ = Path(__file__).resolve().parents[1]
EXEMPLO = (RAIZ / "exemplos" / "perfil-ficticio" / "dossie.md").read_text(encoding="utf-8")
FIXTURES = Path(__file__).parent / "fixtures" / "vagas"


@pytest.fixture
def cliente():
    return TestClient(create_app(), base_url=ORIGEM, headers={"Origin": ORIGEM})


@pytest.fixture
def ana(pasta_dados):
    """Modo manual, com o dossiê de exemplo."""
    perfil = criar_perfil(pasta_dados, "Ana Exemplo", "ana")
    caminho_dossie(pasta_dados, "ana").write_text(EXEMPLO, encoding="utf-8")
    return perfil


@pytest.fixture
def ana_api(ana, pasta_dados):
    perfil = ana.model_copy(update={"ia": ConfigIA().com_provedor("anthropic")})
    salvar_perfil(pasta_dados, perfil)
    return perfil


def _colar(cliente, entrada=VAGA):
    return cliente.post("/p/ana/vagas", data={"entrada": entrada}, follow_redirects=False)


def test_menu_tem_vagas_e_inicio_tem_o_campo(cliente, ana):
    inicio = cliente.get("/p/ana").text
    assert 'href="/p/ana/vagas"' in inicio.split("</nav>")[0]
    assert 'action="/p/ana/vagas"' in inicio
    assert "Nenhuma vaga ainda" in cliente.get("/p/ana/vagas").text


def test_colar_avaliar_e_ver_forcas_e_lacunas(cliente, ana_api, usar_modelo):
    usar_modelo(Falso(SAIDA))
    resposta = _colar(cliente)
    assert resposta.headers["location"] == "/p/ana/vagas/1/avaliar"
    resposta = cliente.get("/p/ana/vagas/1/avaliar", follow_redirects=False)
    assert resposta.headers["location"] == "/p/ana/vagas/1"

    tela = cliente.get("/p/ana/vagas/1").text
    assert "Gerente de Dados Sênior" in tela
    assert '<span class="faixa faixa-B">B</span> 80' in tela
    assert "Vale a candidatura." in tela
    assert tela.index("<h2>Lacunas</h2>") < tela.index("Kubernetes") < tela.index("<h2>Forças</h2>")
    assert 'href="/p/ana/dossie#F-041"' in tela
    assert 'title="Python, SQL e dbt."' in tela
    assert "Experiência com Python e SQL" in tela  # trecho
    assert "custo: US$" in tela
    assert "Descrição completa da vaga" in tela and "Local: Recife - PE" in tela

    lista = cliente.get("/p/ana/vagas").text
    assert '<span class="faixa faixa-B">B</span> 80' in lista
    assert "Gerente de Dados Sênior" in cliente.get("/p/ana").text


def test_a_mesma_vaga_abre_a_existente(cliente, ana_api, usar_modelo):
    falso = usar_modelo(Falso(SAIDA))
    _colar(cliente)
    cliente.get("/p/ana/vagas/1/avaliar")
    resposta = _colar(cliente, VAGA + "\n")
    assert resposta.headers["location"] == "/p/ana/vagas/1?repetida=1"
    assert "Você já tinha trazido esta vaga" in cliente.get(resposta.headers["location"]).text
    assert falso.chamadas == 1


def test_url_da_vaga(cliente, ana_api, usar_modelo, monkeypatch):
    usar_modelo(Falso({"requisitos": []}))
    pagina = (FIXTURES / "pagina.html").read_text(encoding="utf-8")
    transporte = httpx2.MockTransport(lambda _pedido: httpx2.Response(200, text=pagina))
    monkeypatch.setattr(leitura, "novo_cliente", lambda: httpx2.Client(transport=transporte))

    resposta = _colar(cliente, "  https://carreiras.exemplo.test/vagas/ml-senior?utm_source=x  ")
    assert resposta.status_code == 303
    vaga = servico.obter_vaga(banco_do_perfil("ana"), 1)
    assert vaga.url == "https://carreiras.exemplo.test/vagas/ml-senior"
    assert vaga.titulo == "Engenheira de Machine Learning Sênior"
    cliente.get("/p/ana/vagas/1/avaliar")
    tela = cliente.get("/p/ana/vagas/1").text
    assert "A IA não achou requisitos" in tela
    assert 'href="https://carreiras.exemplo.test/vagas/ml-senior"' in tela


def test_linkedin_pede_o_texto(cliente, ana):
    resposta = _colar(cliente, "https://www.linkedin.com/jobs/view/123")
    assert resposta.status_code == 400
    assert "cole o texto" in resposta.text
    assert "linkedin.com/jobs/view/123" in resposta.text  # o que a pessoa digitou volta


def test_vaga_barrada_nao_gasta_e_pode_ser_forcada(cliente, ana_api, pasta_dados, usar_modelo):
    falso = usar_modelo(Falso(SAIDA))
    perfil = carregar_perfil(pasta_dados, "ana")
    criterios = Criterios(modalidades=["remoto"])
    salvar_perfil(pasta_dados, perfil.model_copy(update={"criterios": criterios}))

    _colar(cliente)
    cliente.get("/p/ana/vagas/1/avaliar")
    tela = cliente.get("/p/ana/vagas/1").text
    assert "⛔ Modalidade presencial; você aceita: remoto." in tela
    assert "Avaliar mesmo assim" in tela
    assert falso.chamadas == 0
    assert "barrada pelos filtros" in cliente.get("/p/ana/vagas").text

    cliente.get("/p/ana/vagas/1/avaliar?forcar=1")
    assert falso.chamadas == 1
    assert '<span class="faixa faixa-B">B</span> 80' in cliente.get("/p/ana/vagas/1").text


def test_modo_manual_volta_para_a_vaga(cliente, ana):
    _colar(cliente)
    resposta = cliente.get("/p/ana/vagas/1/avaliar", follow_redirects=False)
    destino = urlsplit(resposta.headers["location"])
    assert destino.path.startswith("/p/ana/pedidos/P-")
    assert parse_qs(destino.query)["voltar"] == ["/p/ana/vagas/1/avaliar"]

    pedido_id = destino.path.rsplit("/", 1)[1]
    pacote = cliente.get(f"/p/ana/pedidos/{pedido_id}").text
    assert "avaliar_vaga v1" in pacote
    assert "Faixa salarial mínima" not in pacote  # fato nao_enviar_ia

    colado = json.dumps({"pedido": pedido_id, "resposta": SAIDA}, ensure_ascii=False)
    cliente.post(
        f"/p/ana/pedidos/{pedido_id}/resposta",
        data={"resposta": colado, "voltar": "/p/ana/vagas/1/avaliar"},
    )
    tela = cliente.get("/p/ana/vagas/1").text
    assert '<span class="faixa faixa-B">B</span> 80' in tela
    assert "custo: US$ 0,00" in tela


def test_erro_da_ia_mostra_a_mensagem(cliente, ana_api, monkeypatch):
    async def falhar(*_args, **_kwargs):
        raise ErroIA("Limite de uso do provedor atingido.")

    monkeypatch.setattr(servico, "executar_detalhado", falhar)
    _colar(cliente)
    resposta = cliente.get("/p/ana/vagas/1/avaliar")
    assert resposta.status_code == 502
    assert "Limite de uso do provedor atingido." in resposta.text
    assert "Tentar de novo" in resposta.text


def test_mudar_estado(cliente, ana_api, usar_modelo):
    usar_modelo(Falso(SAIDA))
    _colar(cliente)
    cliente.get("/p/ana/vagas/1/avaliar")
    cliente.post("/p/ana/vagas/1/estado", data={"estado": "quero_aplicar"})
    assert servico.obter_vaga(banco_do_perfil("ana"), 1).estado == "quero_aplicar"
    assert cliente.post("/p/ana/vagas/1/estado", data={"estado": "inventado"}).status_code == 422


def test_vaga_inexistente(cliente, ana):
    assert cliente.get("/p/ana/vagas/99").status_code == 404
    assert cliente.get("/p/ana/vagas/99/avaliar").status_code == 404


# --- feedback por requisito ---------------------------------------------------


def _avaliada(cliente, usar_modelo) -> Falso:
    falso = usar_modelo(Falso(SAIDA))
    _colar(cliente)
    cliente.get("/p/ana/vagas/1/avaliar")
    return falso


def _fatos(pasta_dados):
    return {
        f.id: f for f in ler_dossie(caminho_dossie(pasta_dados, "ana").read_text("utf-8")).fatos
    }


def test_lacuna_tem_as_tres_respostas_e_forca_tem_nao_e_bem_assim(cliente, ana_api, usar_modelo):
    _avaliada(cliente, usar_modelo)
    tela = cliente.get("/p/ana/vagas/1").text
    lacuna = tela[tela.index('id="requisito-2"') :]
    assert "Eu tenho isso" in lacuna and "Não tenho" in lacuna
    assert '<option value="ferramenta" selected>' in lacuna  # pela categoria
    forca = tela[tela.index('id="requisito-0"') : tela.index('id="requisito-1"')]
    assert "Não é bem assim" in forca and "Eu tenho isso" not in forca


def test_eu_tenho_isso_vira_fato_e_sobe_a_nota_sem_chamar_a_ia(
    cliente, ana_api, usar_modelo, pasta_dados
):
    falso = _avaliada(cliente, usar_modelo)
    resposta = cliente.post(
        "/p/ana/vagas/1/requisitos/2/tenho",
        data={
            "texto": "Operei clusters Kubernetes em produção — ação contínua.",
            "tipo": "ferramenta",
        },
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    novo = next(f for f in _fatos(pasta_dados).values() if "Kubernetes" in f.texto)
    assert resposta.headers["location"] == f"/p/ana/vagas/1?adicionado={novo.id}#requisito-2"
    assert novo.tipo == "ferramenta"
    assert novo.origem.startswith("resposta_lacuna ")

    tela = cliente.get(f"/p/ana/vagas/1?adicionado={novo.id}").text
    assert '<span class="faixa faixa-A">A</span> 100' in tela
    assert "Adicionado ao dossiê como" in tela
    assert "o dossiê mudou desde então" not in tela  # a avaliação já conta com o fato
    assert "você disse: eu tenho isso" in tela
    assert falso.chamadas == 1


def test_desfazer_tira_o_fato_do_dossie(cliente, ana_api, usar_modelo, pasta_dados):
    _avaliada(cliente, usar_modelo)
    cliente.post(
        "/p/ana/vagas/1/requisitos/2/tenho", data={"texto": "Uso Kubernetes.", "tipo": "ferramenta"}
    )
    cliente.post("/p/ana/vagas/1/requisitos/2/desfazer")
    assert not any("Kubernetes" in f.texto for f in _fatos(pasta_dados).values())
    assert '<span class="faixa faixa-B">B</span> 80' in cliente.get("/p/ana/vagas/1").text


def test_nao_tenho_vai_para_as_lacunas_recorrentes(cliente, ana_api, usar_modelo):
    _avaliada(cliente, usar_modelo)
    cliente.post("/p/ana/vagas/1/requisitos/2/ajuste", data={"acao": "nao_tenho"})
    lista = cliente.get("/p/ana/vagas").text
    assert "Lacunas recorrentes" in lista
    assert "<strong>Kubernetes</strong>" in lista

    cliente.post("/p/ana/vagas/1/requisitos/2/desfazer")
    assert "Lacunas recorrentes" not in cliente.get("/p/ana/vagas").text


def test_nao_se_aplica_e_nao_e_bem_assim(cliente, ana_api, usar_modelo):
    _avaliada(cliente, usar_modelo)
    cliente.post("/p/ana/vagas/1/requisitos/2/ajuste", data={"acao": "nao_se_aplica"})
    tela = cliente.get("/p/ana/vagas/1").text
    assert '<span class="faixa faixa-A">A</span> 100' in tela
    assert "<h2>Fora da nota</h2>" in tela

    cliente.post("/p/ana/vagas/1/requisitos/0/ajuste", data={"acao": "nao_e_bem_assim"})
    assert '<span class="faixa faixa-D">D</span> 50' in cliente.get("/p/ana/vagas/1").text


def test_feedback_invalido(cliente, ana_api, usar_modelo):
    _avaliada(cliente, usar_modelo)
    resposta = cliente.post(
        "/p/ana/vagas/1/requisitos/2/tenho", data={"texto": " ", "tipo": "ferramenta"}
    )
    assert resposta.status_code == 400
    assert "Não deu para registrar" in resposta.text
    assert (
        cliente.post("/p/ana/vagas/1/requisitos/9/ajuste", data={"acao": "nao_tenho"}).status_code
        == 404
    )
    assert (
        cliente.post("/p/ana/vagas/1/requisitos/2/ajuste", data={"acao": "tenho"}).status_code
        == 422
    )


def test_vaga_sem_avaliacao_nao_aceita_feedback(cliente, ana):
    _colar(cliente)
    resposta = cliente.post("/p/ana/vagas/1/requisitos/0/ajuste", data={"acao": "nao_tenho"})
    assert resposta.status_code == 404


def test_faixa_esperada_e_concordancia(cliente, ana_api, usar_modelo):
    _avaliada(cliente, usar_modelo)
    assert "Qual faixa você daria" in cliente.get("/p/ana/vagas/1").text
    assert "Concordância" not in cliente.get("/p/ana/vagas").text

    cliente.post("/p/ana/vagas/1/faixa", data={"faixa": "B"})
    assert "bate com o JobFit" in cliente.get("/p/ana/vagas/1").text
    lista = cliente.get("/p/ana/vagas").text
    assert "<strong>1 de 1</strong>" in lista and "(100%)" in lista

    cliente.post("/p/ana/vagas/1/faixa", data={"faixa": "D"})
    assert "o JobFit deu B" in cliente.get("/p/ana/vagas/1").text
    lista = cliente.get("/p/ana/vagas").text
    assert "<strong>0 de 1</strong>" in lista and "(você D, JobFit B)" in lista

    cliente.post("/p/ana/vagas/1/faixa", data={"faixa": ""})
    assert "Concordância" not in cliente.get("/p/ana/vagas").text
    assert cliente.post("/p/ana/vagas/1/faixa", data={"faixa": "E"}).status_code == 422
