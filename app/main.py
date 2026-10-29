from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.web import rotas
from app.web.seguranca import ProtecaoLocal

PASTA_STATIC = Path(__file__).parent / "web" / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="JobFit", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(ProtecaoLocal)
    app.mount("/static", StaticFiles(directory=PASTA_STATIC), name="static")
    app.include_router(rotas.router)

    @app.exception_handler(rotas.PastaNaoConfigurada)
    async def pedir_pasta(_request: Request, _erro: rotas.PastaNaoConfigurada):
        return RedirectResponse("/configurar-pasta", status_code=303)

    return app
