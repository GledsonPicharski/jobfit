from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic_ai.exceptions import (
    ModelAuthenticationError,
    ModelConnectionError,
    ModelHTTPError,
    ModelRateLimitError,
)
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage
from sqlmodel import Session, select

from app.db import banco_do_perfil
from app.ia import ErroIA, TetoAtingido, executar, executar_detalhado
from app.ia.modelos import ChamadaIA
from app.ia.tarefas import TESTAR_CONEXAO
from app.perfis.modelos import Perfil

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def perfil() -> Perfil:
    return Perfil(slug="ana", nome="Ana", criado_em=datetime.now(UTC))


@pytest.fixture
def engine(perfil):
    return banco_do_perfil(perfil.slug)


class Falso:
    """Modelo falso que responde a saída dada e conta as chamadas."""

    def __init__(self, *respostas, custo=Decimal("0.00125")):
        self.respostas = list(respostas) or [{"ok": True, "mensagem": "Conexão funcionando."}]
        self.custo = custo
        self.chamadas = 0
        self.ultimo_pedido = None

    def __call__(self, mensagens, info):
        self.chamadas += 1
        self.ultimo_pedido = mensagens
        resposta = self.respostas[min(self.chamadas, len(self.respostas)) - 1]
        if isinstance(resposta, Exception):
            raise resposta
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, resposta)],
            usage=RequestUsage(input_tokens=1000, output_tokens=40, cost=self.custo),
        )


@pytest.fixture
def usar_modelo(monkeypatch):
    def instalar(falso: Falso) -> Falso:
        monkeypatch.setattr(
            "app.ia.execucao.montar_modelo",
            lambda _perfil, _nivel: FunctionModel(falso, model_name="falso"),
        )
        return falso

    return instalar


def _chamadas(engine) -> list[ChamadaIA]:
    with Session(engine) as sessao:
        return list(sessao.exec(select(ChamadaIA).order_by(ChamadaIA.id)))


async def test_sucesso_devolve_saida_e_registra_custo(perfil, engine, usar_modelo):
    usar_modelo(Falso())

    resultado = await executar_detalhado(perfil, TESTAR_CONEXAO, "ping", engine=engine)

    assert resultado.saida.ok is True
    [chamada] = _chamadas(engine)
    assert chamada == resultado.chamada
    assert chamada.tarefa == "testar_conexao"
    assert chamada.versao_prompt == TESTAR_CONEXAO.versao
    assert (chamada.provedor, chamada.modelo) == ("anthropic", "claude-haiku-5-5")
    assert (chamada.tokens_entrada, chamada.tokens_saida) == (1000, 40)
    assert chamada.custo_micro_usd == 1250
    assert chamada.sucesso and not chamada.cache_hit
    assert chamada.duracao_ms >= 0


async def test_prompt_versionado_vai_como_instrucao(perfil, engine, usar_modelo):
    falso = usar_modelo(Falso())
    await executar(perfil, TESTAR_CONEXAO, "ping", engine=engine)
    assert "JobFit" in falso.ultimo_pedido[0].instructions


async def test_segunda_chamada_vem_do_cache_sem_custo(perfil, engine, usar_modelo):
    falso = usar_modelo(Falso())

    primeira = await executar(perfil, TESTAR_CONEXAO, "ping", engine=engine)
    segunda = await executar(perfil, TESTAR_CONEXAO, "ping", engine=engine)

    assert primeira == segunda
    assert falso.chamadas == 1
    _, cacheada = _chamadas(engine)
    assert cacheada.cache_hit and cacheada.custo_micro_usd == 0
    assert (cacheada.tokens_entrada, cacheada.tokens_saida) == (0, 0)


async def test_sem_cache_sempre_chama_o_modelo(perfil, engine, usar_modelo):
    falso = usar_modelo(Falso())
    await executar(perfil, TESTAR_CONEXAO, "ping", engine=engine, usar_cache=False)
    await executar(perfil, TESTAR_CONEXAO, "ping", engine=engine, usar_cache=False)
    assert falso.chamadas == 2
    assert not any(c.cache_hit for c in _chamadas(engine))


async def test_trocar_modelo_nao_reaproveita_cache(perfil, engine, usar_modelo):
    falso = usar_modelo(Falso())
    await executar(perfil, TESTAR_CONEXAO, "ping", engine=engine)
    perfil.ia.modelos["barato"] = "outro-modelo"
    await executar(perfil, TESTAR_CONEXAO, "ping", engine=engine)
    assert falso.chamadas == 2


async def test_saida_invalida_tenta_de_novo_uma_vez(perfil, engine, usar_modelo):
    falso = usar_modelo(Falso({"ok": "talvez"}, {"ok": True, "mensagem": "Agora sim."}))
    saida = await executar(perfil, TESTAR_CONEXAO, "ping", engine=engine)
    assert saida.mensagem == "Agora sim."
    assert falso.chamadas == 2


async def test_saida_invalida_duas_vezes_vira_erro(perfil, engine, usar_modelo):
    falso = usar_modelo(Falso({"ok": "talvez"}))
    with pytest.raises(ErroIA, match="fora do formato"):
        await executar(perfil, TESTAR_CONEXAO, "ping", engine=engine)
    assert falso.chamadas == 2
    [chamada] = _chamadas(engine)
    assert not chamada.sucesso
    assert chamada.custo_micro_usd is None


@pytest.mark.parametrize(
    ("erro", "mensagem"),
    [
        (ModelHTTPError(401, "falso", body={"error": "invalid x-api-key"}), "Chave inválida"),
        (ModelAuthenticationError("falso", "unauthorized"), "Chave inválida"),
        (ModelHTTPError(404, "falso"), "Modelo não encontrado"),
        (ModelRateLimitError("falso", "slow down"), "Limite de uso"),
        (ModelHTTPError(429, "falso"), "Limite de uso"),
        (ModelConnectionError("falso", "dns"), "Sem conexão"),
        (ModelHTTPError(503, "falso"), "indisponível"),
    ],
)
async def test_erros_do_provedor_viram_mensagem_clara(perfil, engine, usar_modelo, erro, mensagem):
    usar_modelo(Falso(erro))
    with pytest.raises(ErroIA, match=mensagem):
        await executar(perfil, TESTAR_CONEXAO, "ping", engine=engine)

    [chamada] = _chamadas(engine)
    assert not chamada.sucesso
    assert chamada.erro.startswith(type(erro).__name__)


async def test_registro_de_erro_nao_guarda_conteudo(perfil, engine, usar_modelo):
    segredo = "TEXTO-DO-DOSSIE-123"
    usar_modelo(Falso(ModelHTTPError(500, "falso", body={"eco": segredo})))
    with pytest.raises(ErroIA):
        await executar(perfil, TESTAR_CONEXAO, segredo, engine=engine)
    [chamada] = _chamadas(engine)
    assert segredo not in (chamada.erro or "")


async def test_teto_atingido_nao_chama_o_modelo(perfil, engine, usar_modelo):
    falso = usar_modelo(Falso())
    with Session(engine) as sessao:
        sessao.add(
            ChamadaIA(
                tarefa="t", versao_prompt=1, provedor="p", modelo="m", custo_micro_usd=2_000_000
            )
        )
        sessao.commit()

    with pytest.raises(TetoAtingido):
        await executar(perfil, TESTAR_CONEXAO, "ping", engine=engine)
    assert falso.chamadas == 0


async def test_teto_nao_bloqueia_resposta_do_cache(perfil, engine, usar_modelo):
    falso = usar_modelo(Falso(custo=Decimal("2.5")))
    await executar(perfil, TESTAR_CONEXAO, "ping", engine=engine)
    await executar(perfil, TESTAR_CONEXAO, "ping", engine=engine)
    assert falso.chamadas == 1


async def test_custo_desconhecido_fica_nulo(perfil, engine, usar_modelo):
    usar_modelo(Falso(custo=None))
    resultado = await executar_detalhado(perfil, TESTAR_CONEXAO, "ping", engine=engine)
    assert resultado.chamada.custo_micro_usd is None
