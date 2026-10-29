"""Leitura e gravação de texto: sempre UTF-8, quebras de linha LF e gravação atômica.

O Windows não usa UTF-8 por padrão, então nenhum módulo deve abrir arquivo de texto
sem passar por aqui (ou sem `encoding="utf-8"` explícito).
"""

import os
import tempfile
from pathlib import Path


def ler_texto(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def gravar_texto(caminho: Path, conteudo: str) -> None:
    """Grava num temporário na mesma pasta e troca pelo destino só no fim.

    Se o app fechar no meio, o arquivo anterior continua inteiro.
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(dir=caminho.parent, prefix=f".{caminho.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    except BaseException:
        Path(temporario).unlink(missing_ok=True)
        raise
