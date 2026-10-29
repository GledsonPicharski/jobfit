class ErroIA(Exception):
    """Erro da camada de IA com mensagem pronta para a tela, em português."""

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


class ChaveAusente(ErroIA):
    pass


class TetoAtingido(ErroIA):
    pass
