"""Arquivos enviados pela pessoa: limite de tamanho, nome seguro e cópia em `fontes/`."""

import re
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import BinaryIO

LIMITE_BYTES = 10 * 1024 * 1024
LIMITE_TEXTO = "10 MB"


class ErroArquivo(ValueError):
    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status = status


def nome_seguro(nome: str) -> str:
    """Só o nome (sem pasta, em qualquer sistema), sem caracteres que o Windows recusa."""
    base = PureWindowsPath(nome or "").name  # separa por / e por \
    base = re.sub(r"[^\w.]+", "_", base).strip("._")
    return base[:80] or "arquivo"


def ler_enviado(arquivo: BinaryIO) -> bytes:
    conteudo = arquivo.read(LIMITE_BYTES + 1)
    if len(conteudo) > LIMITE_BYTES:
        raise ErroArquivo(413, f"O arquivo é grande demais; o limite é {LIMITE_TEXTO}.")
    if not conteudo:
        raise ErroArquivo(400, "O arquivo está vazio.")
    return conteudo


def salvar_fonte(pasta_perfil: Path, nome: str, conteudo: bytes) -> str:
    """Grava o original em `fontes/` e devolve o caminho relativo à pasta do perfil."""
    pasta = pasta_perfil / "fontes"
    pasta.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    destino = pasta / f"{carimbo}_{nome_seguro(nome)}"
    n = 1
    while destino.exists():
        n += 1
        destino = pasta / f"{carimbo}-{n}_{nome_seguro(nome)}"
    destino.write_bytes(conteudo)
    return destino.relative_to(pasta_perfil).as_posix()
