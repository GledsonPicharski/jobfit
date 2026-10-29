"""Camada de IA. O resto do app só usa o que é exportado aqui."""

import os

# O Pydantic AI imprime um banner no terminal na primeira execução.
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from app.ia.erros import ChaveAusente, ErroIA, TetoAtingido
from app.ia.execucao import ResultadoIA, executar, executar_detalhado

__all__ = [
    "ChaveAusente",
    "ErroIA",
    "ResultadoIA",
    "TetoAtingido",
    "executar",
    "executar_detalhado",
]
