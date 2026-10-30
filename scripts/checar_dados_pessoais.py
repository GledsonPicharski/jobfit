"""Barra commit com dados pessoais: CPF, e-mail real, valor em R$, celular e a lista local.

Uso: `uv run python scripts/checar_dados_pessoais.py [arquivos...]`. Sem arquivos,
verifica tudo que o git rastreia. Roda no pre-commit e na CI.

Nomes, e-mails e valores reais não podem estar neste repositório público, então
ficam em `.dados-sensiveis.txt` (um termo por linha, fora do git). A saída mascara o
que encontrou, porque o log da CI é público.
"""

import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LISTA_LOCAL = RAIZ / ".dados-sensiveis.txt"

DOMINIOS_PERMITIDOS = (
    "exemplo.com",
    "exemplo.com.br",
    "example.com",
    "example.org",
    "example.net",
    "anthropic.com",
    "github.com",
    "users.noreply.github.com",
)
IGNORAR = {"uv.lock"}

_CPF = re.compile(r"(?<![\w.])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\w])")
# A barra invertida no lookbehind evita "\n@decorador" em código-fonte.
_EMAIL = re.compile(r"(?<![\w.+\\-])[\w.+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})")
_REAIS = re.compile(r"R\$\s?\d")
_CELULAR = re.compile(r"(?<!\w)\(?\d{2}\)?\s?9\d{4}[-\s]?\d{4}(?!\w)")


@dataclass(frozen=True)
class Achado:
    linha: int
    tipo: str
    trecho: str


def cpf_valido(texto: str) -> bool:
    digitos = [int(d) for d in re.sub(r"\D", "", texto)]
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(d * peso for d, peso in zip(digitos, range(tamanho + 1, 1, -1), strict=False))
        if digitos[tamanho] != (0 if soma % 11 < 2 else 11 - soma % 11):
            return False
    return True


def _email_permitido(dominio: str) -> bool:
    dominio = dominio.lower()
    return any(dominio == d or dominio.endswith("." + d) for d in DOMINIOS_PERMITIDOS)


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.casefold()


def _mascarar(trecho: str) -> str:
    return trecho[:2] + "*" * max(len(trecho) - 2, 3)


def verificar_texto(texto: str, termos: list[str]) -> list[Achado]:
    termos_norm = [(t, _normalizar(t)) for t in termos]
    achados = []
    for numero, linha in enumerate(texto.splitlines(), start=1):
        cpfs = [m for m in _CPF.finditer(linha) if cpf_valido(m.group())]
        achados += [Achado(numero, "CPF", m.group()) for m in cpfs]
        for m in _EMAIL.finditer(linha):
            if not _email_permitido(m.group(1)):
                achados.append(Achado(numero, "e-mail", m.group()))
        for m in _REAIS.finditer(linha):
            achados.append(Achado(numero, "valor em R$", m.group()))
        for m in _CELULAR.finditer(linha):
            # 11 dígitos seguidos podem ser CPF e celular; já contou como CPF.
            if not any(c.start() <= m.start() < c.end() for c in cpfs):
                achados.append(Achado(numero, "telefone", m.group()))
        linha_norm = _normalizar(linha)
        for termo, termo_norm in termos_norm:
            if termo_norm in linha_norm:
                achados.append(Achado(numero, "lista local", termo))
    return achados


def ler_lista_local(caminho: Path) -> list[str]:
    if not caminho.is_file():
        return []
    termos = (linha.strip() for linha in caminho.read_text(encoding="utf-8").splitlines())
    return [t for t in termos if len(t) >= 3 and not t.startswith("#")]


def _arquivos_do_git() -> list[str]:
    saida = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, check=True, cwd=Path.cwd()
    ).stdout
    return [nome for nome in saida.decode("utf-8").split("\0") if nome]


def main(argumentos: list[str]) -> int:
    termos = ler_lista_local(LISTA_LOCAL)
    arquivos = argumentos or _arquivos_do_git()
    total = 0
    for nome in arquivos:
        caminho = Path(nome)
        if caminho.name in IGNORAR or not caminho.is_file():
            continue
        try:
            texto = caminho.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binário
        for achado in verificar_texto(texto, termos):
            total += 1
            print(f"{nome}:{achado.linha}: {achado.tipo} ({_mascarar(achado.trecho)})")
    if total:
        print(
            f"\n{total} possível(is) dado(s) pessoal(is). Remova antes do commit; "
            "testes e demos usam exemplos/perfil-ficticio/."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
