"""O `.gitignore` bloqueia pastas de dados (`perfis/`, `historico/`...) que o código também usa."""

import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
PASTAS_DE_CODIGO = ("app", "tests", "exemplos", "prompts", "scripts")


@pytest.mark.skipif(shutil.which("git") is None, reason="git não instalado")
def test_nenhum_arquivo_de_codigo_e_ignorado_pelo_git():
    arquivos = [
        str(arquivo.relative_to(RAIZ))
        for pasta in PASTAS_DE_CODIGO
        for arquivo in (RAIZ / pasta).rglob("*")
        if arquivo.is_file() and "__pycache__" not in arquivo.parts
    ]
    resultado = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        input="\n".join(arquivos),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=RAIZ,
        check=False,
    )
    assert resultado.stdout.split() == []
