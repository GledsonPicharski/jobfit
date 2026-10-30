"""Camada de IA. O resto do app só usa o que é exportado aqui."""

import os

# O Pydantic AI imprime um banner no terminal na primeira execução.
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from app.ia.erros import (
    AguardandoResposta,
    ChaveAusente,
    ErroIA,
    PedidoIndisponivel,
    RespostaInvalida,
    TetoAtingido,
)
from app.ia.execucao import executar, executar_detalhado
from app.ia.registro import ResultadoIA

__all__ = [
    "AguardandoResposta",
    "ChaveAusente",
    "ErroIA",
    "PedidoIndisponivel",
    "RespostaInvalida",
    "ResultadoIA",
    "TetoAtingido",
    "executar",
    "executar_detalhado",
]
