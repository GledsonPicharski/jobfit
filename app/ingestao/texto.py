"""Texto colado ou arquivo `.md`/`.txt`: decodificar e escolher as seções que vão para a IA.

Cada seção leva só o próprio conteúdo, do título até o título seguinte (de qualquer
nível). Assim dá para marcar a Parte A e deixar a Parte B de fora, subseção por subseção.
"""

import re
from dataclasses import dataclass

LIMITE_CARACTERES = 60_000  # o que vai para a IA numa importação só
ANTES_DO_TITULO = "Antes do primeiro título"

_TITULO = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$")
_CERCA = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Secao:
    indice: int
    nivel: int  # 0 = o que vem antes do primeiro título
    titulo: str
    inicio: int  # linha do título (ou 0)
    fim: int  # linha seguinte à última, exclusiva
    caracteres: int


def decodificar(conteudo: bytes) -> str:
    """UTF-8 (com ou sem BOM); se não for, o cp1252 do Bloco de Notas antigo."""
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("cp1252", errors="replace")
    return texto.replace("\r\n", "\n").replace("\r", "\n")


def _titulos(linhas: list[str]) -> list[tuple[int, int, str]]:
    titulos = []
    cerca = None
    for i, linha in enumerate(linhas):
        if m := _CERCA.match(linha):
            if cerca is None:
                cerca = m.group(1)
            elif cerca == m.group(1):
                cerca = None
            continue
        if cerca is None and (m := _TITULO.match(linha)):
            titulos.append((i, len(m.group(1)), m.group(2).strip()))
    return titulos


def _trecho(linhas: list[str], inicio: int, fim: int) -> str:
    return "\n".join(linhas[inicio:fim]).strip("\n")


def secoes(texto: str) -> list[Secao]:
    linhas = texto.split("\n")
    titulos = _titulos(linhas)
    limites = []
    primeiro = titulos[0][0] if titulos else len(linhas)
    if _trecho(linhas, 0, primeiro).strip():
        limites.append((0, 0, ANTES_DO_TITULO, primeiro))
    for n, (linha, nivel, titulo) in enumerate(titulos):
        fim = titulos[n + 1][0] if n + 1 < len(titulos) else len(linhas)
        limites.append((linha, nivel, titulo, fim))
    return [
        Secao(i, nivel, titulo, inicio, fim, len(_trecho(linhas, inicio, fim)))
        for i, (inicio, nivel, titulo, fim) in enumerate(limites)
    ]


def texto_das_secoes(texto: str, indices: list[int]) -> str:
    """O texto das seções marcadas, na ordem do arquivo."""
    linhas = texto.split("\n")
    marcadas = set(indices)
    partes = [_trecho(linhas, s.inicio, s.fim) for s in secoes(texto) if s.indice in marcadas]
    return "\n\n".join(p for p in partes if p.strip())
