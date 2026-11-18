"""Pré-nota de uma vaga: estimativa por palavras, em código e local (decisão 0009).

É a parte dos termos conhecidos que a vaga cita (glossário em `config/termos.yaml`, mais
as ferramentas e competências do dossiê) que também aparece nos fatos confirmados. Serve
só para ordenar as vagas novas sem gastar token; a nota de verdade vem da avaliação.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.arquivos import ler_texto
from app.dossie.modelos import Fato
from app.textos import contem, palavras

GLOSSARIO = Path(__file__).resolve().parents[2] / "config" / "termos.yaml"
_TIPOS_TERMO = ("ferramenta", "competencia", "certificacao")
_MAX_PALAVRAS_TERMO = 4


@dataclass(frozen=True)
class Prenota:
    valor: int | None  # None: a vaga não cita nenhum termo conhecido
    encontrados: list[str] = field(default_factory=list)
    faltando: list[str] = field(default_factory=list)


def carregar_vocabulario(caminho: Path = GLOSSARIO) -> list[list[str]]:
    return [[str(t) for t in grupo] for grupo in yaml.safe_load(ler_texto(caminho)) or []]


def _no_texto(texto: str, grupo: list[str]) -> bool:
    return any(contem(texto, termo) for termo in grupo)


def termos_do_dossie(fatos: list[Fato], vocab: list[list[str]]) -> tuple[set[str], list[list[str]]]:
    """Os termos (pelo nome canônico) que o dossiê tem, e o vocabulário com os do dossiê.

    Contam só fatos confirmados; contato não diz nada sobre o que a pessoa sabe fazer.
    """
    validos = [f for f in fatos if f.status == "confirmado" and f.tipo != "contato"]
    vocab = [list(g) for g in vocab]
    for fato in validos:
        curto = len(palavras(fato.texto).split()) <= _MAX_PALAVRAS_TERMO
        novo = not any(_no_texto(fato.texto, g) for g in vocab)
        if fato.tipo in _TIPOS_TERMO and curto and novo:
            vocab.append([fato.texto.strip().casefold()])
    textos = [" ".join(filter(None, (f.texto, f.cargo))) for f in validos]
    presentes = {g[0] for g in vocab if any(_no_texto(t, g) for t in textos)}
    return presentes, vocab


def calcular_prenota(texto_vaga: str, termos: set[str], vocab: list[list[str]]) -> Prenota:
    citados = [g[0] for g in vocab if _no_texto(texto_vaga, g)]
    if not citados:
        return Prenota(None)
    encontrados = [t for t in citados if t in termos]
    faltando = [t for t in citados if t not in termos]
    return Prenota(round(100 * len(encontrados) / len(citados)), encontrados, faltando)
