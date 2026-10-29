"""Proteção do servidor local contra DNS rebinding, CSRF e iframes.

- `Host` tem de ser 127.0.0.1 ou localhost: barra DNS rebinding, em que um domínio
  externo passa a apontar para 127.0.0.1 e lê as respostas do app.
- Métodos que alteram dados exigem `Origin` (ou `Referer`) igual ao próprio app:
  barra o POST que qualquer site aberto no navegador consegue mandar para cá.
"""

from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HOSTS_LOCAIS = frozenset({"127.0.0.1", "localhost"})
METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS"})
CABECALHOS = {
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}


def _hostname(host: str) -> str | None:
    return urlsplit(f"//{host}").hostname if host else None


def _origem_do_pedido(cabecalhos: Headers) -> str | None:
    if origem := cabecalhos.get("origin"):
        return None if origem == "null" else urlsplit(origem).netloc.lower()
    if referer := cabecalhos.get("referer"):
        return urlsplit(referer).netloc.lower()
    return None


class ProtecaoLocal:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cabecalhos = Headers(scope=scope)
        host = cabecalhos.get("host", "").lower()
        if _hostname(host) not in HOSTS_LOCAIS:
            await PlainTextResponse("Host não permitido.", status_code=400)(scope, receive, send)
            return
        if scope["method"] not in METODOS_SEGUROS and _origem_do_pedido(cabecalhos) != host:
            resposta = PlainTextResponse("Pedido de outra origem recusado.", status_code=403)
            await resposta(scope, receive, send)
            return

        async def enviar_com_cabecalhos(mensagem: Message) -> None:
            if mensagem["type"] == "http.response.start":
                MutableHeaders(scope=mensagem).update(CABECALHOS)
            await send(mensagem)

        await self.app(scope, receive, enviar_com_cabecalhos)
