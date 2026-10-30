"""`executar()`: a única porta de saída para provedores de IA.

Ordem: cache → teto diário → modelo do provedor → prompt versionado → chamada com
saída validada (uma nova tentativa se vier inválida) → registro de custo → cache.
Toda chamada que chega ao provedor é registrada em `chamadas_ia`, com sucesso ou erro.
"""

import time

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelHTTPError,
    ModelNotFoundError,
    ModelQuotaExceededError,
    ModelRateLimitError,
    ModelServerError,
    ModelUnavailableError,
    UnexpectedModelBehavior,
)
from sqlalchemy import Engine
from sqlmodel import Session

from app.ia.cache import chave_cache, gravar_cache, ler_cache
from app.ia.custos import checar_teto, para_micro_usd
from app.ia.erros import ErroIA
from app.ia.modelos import ChamadaIA
from app.ia.prompts import carregar_prompt
from app.ia.provedores import montar_modelo
from app.ia.registro import ResultadoIA, registrar
from app.ia.tarefas import Tarefa, texto_da_entrada
from app.perfis.modelos import Perfil


def _status(erro: Exception) -> int | None:
    return erro.status_code if isinstance(erro, ModelHTTPError) else None


def _detalhe_do_provedor(erro: Exception) -> str | None:
    """Mensagem original do provedor, para a tela. Nunca vai para o banco nem para o log."""
    if not isinstance(erro, ModelAPIError):
        return None
    if isinstance(erro, ModelHTTPError):
        corpo = erro.body
        if isinstance(corpo, dict) and isinstance(corpo.get("error"), dict):
            texto = corpo["error"].get("message")
        elif isinstance(corpo, dict):
            texto = corpo.get("message")
        else:
            texto = corpo
    else:
        texto = erro.message
    if not texto:
        return None
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= 300 else texto[:300] + "…"


def traduzir_erro(erro: Exception, modelo: str) -> ErroIA:
    traduzido = _traduzir(erro, modelo)
    if detalhe := _detalhe_do_provedor(erro):
        return ErroIA(f"{traduzido.mensagem} Resposta do provedor: {detalhe}")
    return traduzido


def _traduzir(erro: Exception, modelo: str) -> ErroIA:
    status = _status(erro)
    if isinstance(erro, ModelAuthenticationError) or status in (401, 403):
        return ErroIA("Chave inválida ou sem permissão no provedor. Confira a chave cadastrada.")
    if isinstance(erro, ModelNotFoundError) or status == 404:
        return ErroIA(
            f"O provedor não encontrou um servidor para o modelo {modelo}. Confira o nome; "
            "no OpenRouter, modelos :free também exigem liberar a privacidade da conta."
        )
    if isinstance(erro, ModelRateLimitError | ModelQuotaExceededError) or status == 429:
        return ErroIA(
            "Limite de uso do provedor atingido. Confira seus créditos ou tente mais tarde."
        )
    if isinstance(erro, ModelConnectionError):
        return ErroIA("Sem conexão com o provedor. Confira a internet e tente de novo.")
    if isinstance(erro, ModelServerError | ModelUnavailableError) or (status or 0) >= 500:
        return ErroIA("O provedor de IA está indisponível agora. Tente de novo em alguns minutos.")
    if isinstance(erro, UnexpectedModelBehavior):
        return ErroIA("A resposta da IA veio fora do formato esperado, mesmo após nova tentativa.")
    if isinstance(erro, ModelAPIError):
        return ErroIA(f"O provedor recusou o pedido ({type(erro).__name__}).")
    return ErroIA(f"Erro inesperado ao chamar a IA ({type(erro).__name__}).")


def _resumo_erro(erro: Exception) -> str:
    """Só o tipo e o status: a mensagem do provedor pode ecoar o conteúdo enviado."""
    status = _status(erro)
    return type(erro).__name__ + (f" (HTTP {status})" if status else "")


async def executar_detalhado[S: BaseModel](
    perfil: Perfil,
    tarefa: Tarefa[S],
    entrada: str | BaseModel,
    *,
    engine: Engine,
    usar_cache: bool = True,
) -> ResultadoIA[S]:
    provedor = perfil.ia.provedor
    modelo = perfil.ia.modelos[tarefa.nivel]

    def nova_chamada(**campos) -> ChamadaIA:
        return ChamadaIA(
            tarefa=tarefa.nome,
            versao_prompt=tarefa.versao,
            provedor=provedor,
            modelo=modelo,
            **campos,
        )

    chave = chave_cache(tarefa.nome, tarefa.versao, f"{provedor}:{modelo}", entrada)
    if usar_cache:
        with Session(engine) as sessao:
            guardado = ler_cache(sessao, chave)
        if guardado is not None:
            saida = tarefa.saida.model_validate_json(guardado.saida_json)
            return ResultadoIA(
                saida, registrar(engine, nova_chamada(custo_micro_usd=0, cache_hit=True))
            )

    checar_teto(engine, perfil.ia.teto_diario_usd)
    agente = Agent(
        montar_modelo(perfil, tarefa.nivel),
        output_type=tarefa.saida,
        instructions=carregar_prompt(tarefa.nome, tarefa.versao),
        retries=1,
    )

    inicio = time.perf_counter()
    try:
        resultado = await agente.run(texto_da_entrada(entrada))
    except Exception as erro:
        duracao = int((time.perf_counter() - inicio) * 1000)
        registrar(engine, nova_chamada(sucesso=False, erro=_resumo_erro(erro), duracao_ms=duracao))
        raise traduzir_erro(erro, modelo) from erro
    duracao = int((time.perf_counter() - inicio) * 1000)

    uso = resultado.usage
    chamada = nova_chamada(
        tokens_entrada=uso.input_tokens,
        tokens_saida=uso.output_tokens,
        custo_micro_usd=para_micro_usd(uso.cost),
        duracao_ms=duracao,
    )
    if usar_cache:
        with Session(engine) as sessao:
            gravar_cache(
                sessao,
                chave,
                tarefa=tarefa.nome,
                versao=tarefa.versao,
                modelo=f"{provedor}:{modelo}",
                saida_json=resultado.output.model_dump_json(),
            )
            sessao.commit()
    return ResultadoIA(resultado.output, registrar(engine, chamada))


async def executar[S: BaseModel](
    perfil: Perfil,
    tarefa: Tarefa[S],
    entrada: str | BaseModel,
    *,
    engine: Engine,
    usar_cache: bool = True,
) -> S:
    resultado = await executar_detalhado(
        perfil, tarefa, entrada, engine=engine, usar_cache=usar_cache
    )
    return resultado.saida
