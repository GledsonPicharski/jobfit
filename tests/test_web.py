import json
from decimal import Decimal
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import create_app
from app.perfis.modelos import MODELOS_PADRAO, ConfigIA
from app.perfis.servico import carregar_perfil, criar_perfil, salvar_perfil
from tests.ia_falsa import Falso

ORIGEM = "http://127.0.0.1:8765"


@pytest.fixture
def cliente():
    return TestClient(create_app(), base_url=ORIGEM, headers={"Origin": ORIGEM})


@pytest.fixture
def ana(pasta_dados):
    """Perfil novo: nasce no modo manual."""
    return criar_perfil(pasta_dados, "Ana Exemplo")


@pytest.fixture
def ana_api(ana, pasta_dados):
    """Mesmo perfil, no modo API (Anthropic)."""
    perfil = ana.model_copy(update={"ia": ConfigIA().com_provedor("anthropic")})
    salvar_perfil(pasta_dados, perfil)
    return perfil


def test_primeira_execucao_pede_a_pasta(cliente):
    resposta = cliente.get("/", follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/configurar-pasta"
    assert "Pasta de dados" in cliente.get("/configurar-pasta").text


def test_configurar_pasta_com_aspas_espaco_e_acento(cliente, tmp_path):
    pasta = tmp_path / "Meu Drive" / "Currículo – JobFit"
    resposta = cliente.post("/configurar-pasta", data={"pasta": f'"{pasta}"'})

    assert resposta.status_code == 200
    assert "Nenhum perfil ainda" in resposta.text
    assert config.carregar_config().pasta_dados == pasta
    assert pasta.is_dir()


def test_configurar_pasta_relativa_mostra_erro(cliente):
    resposta = cliente.post("/configurar-pasta", data={"pasta": "JobFit"})
    assert resposta.status_code == 400
    assert "caminho completo" in resposta.text
    assert config.carregar_config().pasta_dados is None


def test_criar_perfil_pelo_formulario(cliente, pasta_dados):
    resposta = cliente.post("/perfis", data={"nome": "Ana Exemplo"}, follow_redirects=False)

    assert resposta.headers["location"] == "/p/ana-exemplo/ia"
    assert carregar_perfil(pasta_dados, "ana-exemplo").nome == "Ana Exemplo"
    assert config.carregar_config().ultimo_perfil == "ana-exemplo"
    assert "Ana Exemplo" in cliente.get("/").text


def test_criar_perfil_duplicado_mostra_erro(cliente, ana):
    resposta = cliente.post("/perfis", data={"nome": "Ana Exemplo"})
    assert resposta.status_code == 400
    assert "já existe" in resposta.text


def test_criar_perfil_com_slug_invalido(cliente, pasta_dados):
    resposta = cliente.post("/perfis", data={"nome": "Ana", "slug": "../fora"})
    assert resposta.status_code == 400
    assert not (pasta_dados.parent / "fora").exists()


@pytest.mark.parametrize("url", ["/p/ninguem", "/p/ninguem/ia", "/p/..%2F..%2Fx/ia"])
def test_perfil_inexistente_da_404(cliente, pasta_dados, url):
    assert cliente.get(url).status_code == 404


def test_salvar_chave_vai_para_o_cofre_e_nao_para_arquivo(cliente, ana, pasta_dados, chaveiro):
    chave = "sk-ant-segredo-que-nao-pode-vazar"
    dados = {"provedor": "anthropic", "teto": "2,00", "chave": chave}
    resposta = cliente.post("/p/ana-exemplo/ia", data=dados)

    assert resposta.status_code == 200
    assert "Configuração salva" in resposta.text
    assert chaveiro.segredos[("jobfit", "ana-exemplo:anthropic")] == chave
    assert chave not in resposta.text
    assert "(chave cadastrada)" in resposta.text
    for arquivo in pasta_dados.parent.parent.rglob("*"):
        if arquivo.is_file():
            assert chave.encode() not in arquivo.read_bytes(), arquivo


def test_trocar_provedor_troca_modelos_padrao(cliente, ana_api, pasta_dados):
    dados = {
        "provedor": "openrouter",
        "teto": "2,50",
        "modelo_barato": MODELOS_PADRAO["anthropic"]["barato"],
        "modelo_forte": MODELOS_PADRAO["anthropic"]["forte"],
    }
    cliente.post("/p/ana-exemplo/ia", data=dados)

    ia = carregar_perfil(pasta_dados, "ana-exemplo").ia
    assert ia.provedor == "openrouter"
    assert ia.modelos == MODELOS_PADRAO["openrouter"]
    assert ia.teto_diario_usd == Decimal("2.50")


@pytest.mark.parametrize("teto", ["dois", "-1"])
def test_teto_invalido_mostra_erro(cliente, ana, pasta_dados, teto):
    resposta = cliente.post("/p/ana-exemplo/ia", data={"provedor": "anthropic", "teto": teto})
    assert resposta.status_code == 400
    assert "Teto diário" in resposta.text
    assert carregar_perfil(pasta_dados, "ana-exemplo").ia.teto_diario_usd == Decimal("2.00")


def test_testar_conexao_mostra_resposta_e_custo(cliente, ana_api, usar_modelo):
    usar_modelo(Falso())
    resposta = cliente.post("/p/ana-exemplo/ia/testar")

    assert resposta.status_code == 200
    assert "Conexão funcionando." in resposta.text
    assert "US$ 0,00125" in resposta.text
    assert "<html" not in resposta.text  # fragmento HTMX, não página inteira


def test_testar_conexao_sem_chave_mostra_erro_claro(cliente, ana_api):
    resposta = cliente.post("/p/ana-exemplo/ia/testar")
    assert "Não funcionou" in resposta.text
    assert "Nenhuma chave do Anthropic" in resposta.text


def test_testar_conexao_com_chave_errada_mostra_erro_claro(cliente, ana_api, usar_modelo):
    from pydantic_ai.exceptions import ModelHTTPError

    usar_modelo(Falso(ModelHTTPError(401, "falso")))
    resposta = cliente.post("/p/ana-exemplo/ia/testar")
    assert resposta.status_code == 200
    assert "Chave inválida" in resposta.text


def test_painel_mostra_gasto_do_dia(cliente, ana_api, usar_modelo):
    assert "Nenhuma chamada de IA ainda" in cliente.get("/p/ana-exemplo").text

    usar_modelo(Falso())
    cliente.post("/p/ana-exemplo/ia/testar")
    painel = cliente.get("/p/ana-exemplo").text

    assert "Gasto de IA hoje" in painel
    assert "US$ 0,00125" in painel
    assert "testar_conexao v1" in painel


def test_testar_conexao_nao_usa_cache(cliente, ana_api, usar_modelo):
    falso = usar_modelo(Falso())
    cliente.post("/p/ana-exemplo/ia/testar")
    cliente.post("/p/ana-exemplo/ia/testar")
    assert falso.chamadas == 2


def test_static_vendorizado(cliente):
    assert cliente.get("/static/htmx.min.js").status_code == 200
    assert cliente.get("/static/pico.min.css").status_code == 200


def test_sem_documentacao_automatica_da_api(cliente):
    assert cliente.get("/docs").status_code == 404
    assert cliente.get("/openapi.json").status_code == 404


def test_config_json_legivel(cliente, tmp_path):
    pasta = tmp_path / "Dados – Ação"
    cliente.post("/configurar-pasta", data={"pasta": str(pasta)})
    bruto = config.caminho_config().read_text(encoding="utf-8")
    assert json.loads(bruto)["pasta_dados"] == str(pasta)


# --- modo manual --------------------------------------------------------------


def _resposta_valida(pedido_id: str) -> str:
    return (
        "Aqui está:\n```json\n"
        f'{{"pedido": "{pedido_id}", '
        '"resposta": {"ok": true, "mensagem": "Funcionou pelo chat."}}'
        "\n```"
    )


def _gerar_pedido_de_teste(cliente) -> str:
    resposta = cliente.post("/p/ana-exemplo/ia/testar", follow_redirects=False)
    assert resposta.status_code == 303
    local = resposta.headers["location"]
    assert local.startswith("/p/ana-exemplo/pedidos/P-")
    return local.rsplit("/", 1)[1]


def test_perfil_novo_no_modo_manual_nao_pede_chave(cliente, ana):
    painel = cliente.get("/p/ana-exemplo").text
    assert "Nenhuma chave" not in painel

    tela_ia = cliente.get("/p/ana-exemplo/ia").text
    assert "Testar ciclo" in tela_ia
    assert 'name="chave"' not in tela_ia


def test_ciclo_manual_completo(cliente, ana):
    pedido_id = _gerar_pedido_de_teste(cliente)

    tela = cliente.get(f"/p/ana-exemplo/pedidos/{pedido_id}").text
    assert f"Pedido JobFit {pedido_id}" in tela
    assert "dados_jobfit" in tela
    assert "Copiar" in tela

    resultado = cliente.post(
        f"/p/ana-exemplo/pedidos/{pedido_id}/resposta",
        data={"resposta": _resposta_valida(pedido_id)},
    )
    assert resultado.status_code == 200
    assert "Conexão funcionando." in resultado.text
    assert "Funcionou pelo chat." in resultado.text
    assert "US$ 0,00" in resultado.text

    painel = cliente.get("/p/ana-exemplo").text
    assert "testar_conexao v1" in painel
    assert "aguardando resposta" not in painel


def test_testar_de_novo_reaproveita_o_pedido_pendente(cliente, ana):
    assert _gerar_pedido_de_teste(cliente) == _gerar_pedido_de_teste(cliente)


def test_resposta_invalida_mostra_erro_e_correcao(cliente, ana):
    pedido_id = _gerar_pedido_de_teste(cliente)
    resposta = cliente.post(
        f"/p/ana-exemplo/pedidos/{pedido_id}/resposta",
        data={"resposta": f'{{"pedido": "{pedido_id}", "resposta": {{"ok": true}}}}'},
    )
    assert resposta.status_code == 400
    assert "não seguiu o formato" in resposta.text
    assert "mensagem: campo obrigatório ausente" in resposta.text
    assert 'id="correcao"' in resposta.text


def test_baixar_pacote(cliente, ana):
    pedido_id = _gerar_pedido_de_teste(cliente)
    resposta = cliente.get(f"/p/ana-exemplo/pedidos/{pedido_id}/pacote.md")
    assert resposta.headers["content-type"] == "text/markdown; charset=utf-8"
    assert f'filename="jobfit-{pedido_id}.md"' in resposta.headers["content-disposition"]
    assert "attachment" in resposta.headers["content-disposition"]
    assert f"Pedido JobFit {pedido_id} — testar_conexao" in resposta.content.decode("utf-8")


@pytest.mark.parametrize(
    ("voltar", "redireciona"),
    [
        ("/p/ana-exemplo/ia", True),
        ("//evil.com/p/ana-exemplo/", False),
        ("https://evil.com/p/ana-exemplo/ia", False),
        ("/p/outro/ia", False),
        ("/p/ana-exemplo-falso/ia", False),
        ("", False),
    ],
)
def test_voltar_so_aceita_caminho_do_proprio_perfil(cliente, ana, voltar, redireciona):
    pedido_id = _gerar_pedido_de_teste(cliente)
    resposta = cliente.post(
        f"/p/ana-exemplo/pedidos/{pedido_id}/resposta",
        data={"resposta": _resposta_valida(pedido_id), "voltar": voltar},
        follow_redirects=False,
    )
    if redireciona:
        assert resposta.status_code == 303
        assert resposta.headers["location"] == voltar
    else:
        assert resposta.status_code == 200
        assert "Funcionou pelo chat." in resposta.text


def test_painel_lista_pendentes_e_cancelar_tira_da_lista(cliente, ana):
    pedido_id = _gerar_pedido_de_teste(cliente)
    painel = cliente.get("/p/ana-exemplo").text
    assert "1 pedido(s) aguardando resposta" in painel
    assert f"/p/ana-exemplo/pedidos/{pedido_id}" in painel

    cliente.post(f"/p/ana-exemplo/pedidos/{pedido_id}/cancelar")
    assert "aguardando resposta" not in cliente.get("/p/ana-exemplo").text
    assert "cancelado" in cliente.get(f"/p/ana-exemplo/pedidos/{pedido_id}").text


def test_pedido_respondido_nao_aceita_outra_resposta(cliente, ana):
    pedido_id = _gerar_pedido_de_teste(cliente)
    url = f"/p/ana-exemplo/pedidos/{pedido_id}/resposta"
    cliente.post(url, data={"resposta": _resposta_valida(pedido_id)})
    resposta = cliente.post(url, data={"resposta": _resposta_valida(pedido_id)})
    assert resposta.status_code == 400
    assert "não está mais aguardando" in resposta.text


def test_pedido_de_outro_perfil_da_404(cliente, ana, pasta_dados):
    pedido_id = _gerar_pedido_de_teste(cliente)
    criar_perfil(pasta_dados, "Camila")
    assert cliente.get(f"/p/camila/pedidos/{pedido_id}").status_code == 404
    assert cliente.get("/p/ana-exemplo/pedidos/P-NAOEXI").status_code == 404


def test_handler_leva_qualquer_funcionalidade_ao_pedido(ana):
    """Uma funcionalidade futura só chama executar(); o handler cuida do modo manual."""
    from app.db import banco_do_perfil
    from app.ia import executar
    from app.ia.tarefas import TESTAR_CONEXAO

    app = create_app()

    @app.get("/p/{slug}/funcionalidade")
    async def funcionalidade(slug: str):
        saida = await executar(ana, TESTAR_CONEXAO, "algo", engine=banco_do_perfil(slug))
        return {"mensagem": saida.mensagem}

    cliente = TestClient(app, base_url=ORIGEM, headers={"Origin": ORIGEM})
    resposta = cliente.get("/p/ana-exemplo/funcionalidade?x=1", follow_redirects=False)
    assert resposta.status_code == 303
    local = resposta.headers["location"]
    assert local.startswith("/p/ana-exemplo/pedidos/P-")
    assert local.endswith("?voltar=/p/ana-exemplo/funcionalidade%3Fx%3D1")

    htmx = cliente.get("/p/ana-exemplo/funcionalidade", headers={"HX-Request": "true"})
    assert htmx.headers["hx-redirect"].startswith("/p/ana-exemplo/pedidos/P-")

    pedido_id = urlsplit(local).path.rsplit("/", 1)[1]
    voltou = cliente.post(
        f"/p/ana-exemplo/pedidos/{pedido_id}/resposta",
        data={"resposta": _resposta_valida(pedido_id), "voltar": "/p/ana-exemplo/funcionalidade"},
    )
    assert voltou.json() == {"mensagem": "Funcionou pelo chat."}


# --- excluir perfil -----------------------------------------------------------


def test_tela_de_excluir_pede_confirmacao(cliente, ana):
    assert 'href="/p/ana-exemplo/excluir"' in cliente.get("/p/ana-exemplo/ia").text
    tela = cliente.get("/p/ana-exemplo/excluir")
    assert tela.status_code == 200
    assert "lixeira" in tela.text
    assert 'name="confirmacao"' in tela.text


@pytest.mark.parametrize("confirmacao", ["", "ana", "Ana Exemplo"])
def test_excluir_sem_confirmar_o_identificador_nao_exclui(cliente, ana, pasta_dados, confirmacao):
    resposta = cliente.post("/p/ana-exemplo/excluir", data={"confirmacao": confirmacao})
    assert resposta.status_code == 400
    assert "Digite" in resposta.text
    assert carregar_perfil(pasta_dados, "ana-exemplo") == ana


def test_excluir_perfil_leva_ao_inicio_e_some_da_lista(cliente, ana, pasta_dados):
    resposta = cliente.post(
        "/p/ana-exemplo/excluir", data={"confirmacao": " ana-exemplo "}, follow_redirects=False
    )
    assert resposta.status_code == 303

    inicio = cliente.get(resposta.headers["location"])
    assert "Ana Exemplo" in inicio.text
    assert "lixeira" in inicio.text
    assert 'href="/p/ana-exemplo"' not in inicio.text
    assert cliente.get("/p/ana-exemplo").status_code == 404
    assert len(list((pasta_dados / "lixeira").iterdir())) == 1


def test_excluir_exige_origem_do_proprio_app(ana, pasta_dados):
    sem_origem = TestClient(create_app(), base_url=ORIGEM)
    resposta = sem_origem.post("/p/ana-exemplo/excluir", data={"confirmacao": "ana-exemplo"})
    assert resposta.status_code == 403
    assert carregar_perfil(pasta_dados, "ana-exemplo") == ana
