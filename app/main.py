from pathlib import Path
from urllib.parse import quote, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.ia import AguardandoResposta
from app.web import rotas
from app.web.seguranca import ProtecaoLocal

PASTA_STATIC = Path(__file__).parent / "web" / "static"


def _de_onde_veio(request: Request) -> str:
    """Para onde voltar depois da resposta: a própria URL (GET) ou a página do formulário."""
    if request.method == "GET":
        url = request.url
        return url.path + (f"?{url.query}" if url.query else "")
    return urlsplit(request.headers.get("referer", "")).path


def create_app() -> FastAPI:
    app = FastAPI(title="JobFit", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(ProtecaoLocal)
    app.mount("/static", StaticFiles(directory=PASTA_STATIC), name="static")
    app.include_router(rotas.router)

    @app.exception_handler(rotas.PastaNaoConfigurada)
    async def pedir_pasta(_request: Request, _erro: rotas.PastaNaoConfigurada):
        return RedirectResponse("/configurar-pasta", status_code=303)

    @app.exception_handler(AguardandoResposta)
    async def pedir_resposta(request: Request, aguardando: AguardandoResposta):
        """Modo manual: qualquer funcionalidade que chame executar() cai aqui."""
        slug = request.path_params.get("slug", "")
        url = f"/p/{slug}/pedidos/{aguardando.pedido.id}"
        if voltar := rotas.voltar_seguro(slug, _de_onde_veio(request)):
            url += "?voltar=" + quote(voltar, safe="/")
        if request.headers.get("hx-request"):
            return Response(status_code=200, headers={"HX-Redirect": url})
        return RedirectResponse(url, status_code=303)

    return app
