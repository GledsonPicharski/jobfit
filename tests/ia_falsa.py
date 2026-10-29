"""Modelo de IA falso para testes: responde saídas prontas e conta as chamadas."""

from decimal import Decimal

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.usage import RequestUsage


class Falso:
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
