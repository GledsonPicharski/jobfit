from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ia.modelos import PedidoIA


class ErroIA(Exception):
    """Erro da camada de IA com mensagem pronta para a tela, em português."""

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


class ChaveAusente(ErroIA):
    pass


class TetoAtingido(ErroIA):
    pass


class PedidoIndisponivel(ErroIA):
    pass


class RespostaInvalida(ErroIA):
    """A resposta colada não segue o formato; `correcao` é o texto para colar no chat."""

    def __init__(self, erros: list[str], correcao: str):
        super().__init__("A resposta não seguiu o formato pedido: " + "; ".join(erros))
        self.erros = erros
        self.correcao = correcao


class AguardandoResposta(Exception):
    """Modo manual: a tarefa espera a pessoa colar a resposta do chat."""

    def __init__(self, pedido: "PedidoIA"):
        super().__init__(f"Aguardando resposta do pedido {pedido.id}.")
        self.pedido = pedido
