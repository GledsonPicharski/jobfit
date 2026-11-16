"""`python -m app.mcp --perfil <slug>`: como o Claude Desktop inicia o servidor.

Sem `uv run` nem `jobfit.exe`, para não travar a sincronização do uv com o app aberto.
"""

import argparse

from app.mcp.servidor import criar_servidor


def main() -> None:
    argumentos = argparse.ArgumentParser(prog="python -m app.mcp")
    argumentos.add_argument("--perfil", help="slug do perfil (padrão: o último aberto)")
    criar_servidor(argumentos.parse_args().perfil).run("stdio")


if __name__ == "__main__":
    main()
