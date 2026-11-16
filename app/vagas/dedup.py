"""Deduplicação de vagas em código (decisão 0009).

A mesma vaga é reconhecida, nesta ordem, pela URL normalizada, pelo mesmo texto, ou pela
mesma empresa com título parecido e local compatível. Vale entre portais e contra as vagas
coladas pela pessoa.
"""

from collections import defaultdict
from dataclasses import dataclass

from app.textos import palavras
from app.vagas.leitura import normalizar_url

# Palavras que não mudam qual é a vaga: modalidade, gênero, região e conectivos.
_RUIDO_TITULO = {
    "remote", "remoto", "remota", "hybrid", "hibrido", "onsite", "presencial", "home", "office",
    "latam", "brazil", "brasil", "americas", "anywhere", "worldwide", "global",
    "m", "f", "d", "w", "x", "h", "all", "genders", "pcd", "vaga", "afirmativa",
    "de", "da", "do", "das", "dos", "e", "em", "para", "of", "the", "and", "for", "in", "a",
}  # fmt: skip
_SUFIXOS_EMPRESA = {
    "inc", "ltda", "ltd", "llc", "sa", "s", "a", "gmbh", "corp", "corporation", "co",
    "company", "plc", "bv", "ag", "me", "eireli", "group", "grupo", "holding",
}  # fmt: skip
_LOCAL_NEUTRO = {"remote", "remoto", "remota", "anywhere", "worldwide", "global", "latam"}
_SEMELHANCA_MINIMA = 0.8


@dataclass(frozen=True)
class Candidata:
    url: str | None
    empresa: str | None
    titulo: str | None
    local: str | None
    hash: str | None


def _empresa(nome: str | None) -> str:
    return " ".join(p for p in palavras(nome or "").split() if p not in _SUFIXOS_EMPRESA)


def mesma_empresa(a: str | None, b: str | None) -> bool:
    chave = _empresa(a)
    return bool(chave) and chave == _empresa(b)


def _palavras_titulo(titulo: str | None) -> set[str]:
    return {p for p in palavras(titulo or "").split() if p not in _RUIDO_TITULO}


def titulo_parecido(a: str | None, b: str | None) -> bool:
    """As mesmas palavras, em qualquer ordem, tirando modalidade, região e gênero."""
    pa, pb = _palavras_titulo(a), _palavras_titulo(b)
    if not pa or not pb:
        return False
    return len(pa & pb) / len(pa | pb) >= _SEMELHANCA_MINIMA


def _cidade(local: str | None) -> set[str]:
    return {p for p in palavras(local or "").split() if len(p) > 2} - _LOCAL_NEUTRO


def local_compativel(a: str | None, b: str | None) -> bool:
    """Ausente ou remoto casa com tudo; dois lugares precisam ter algo em comum."""
    ca, cb = _cidade(a), _cidade(b)
    return not ca or not cb or bool(ca & cb) or _so_pais(ca) or _so_pais(cb)


def _so_pais(cidade: set[str]) -> bool:
    return cidade <= {"brazil", "brasil", "mexico", "colombia", "argentina", "chile", "peru"}


class Indice:
    """As vagas conhecidas, para achar a repetida sem varrer o banco a cada vaga."""

    def __init__(self) -> None:
        self._por_url: dict[str, int] = {}
        self._por_hash: dict[str, int] = {}
        self._por_empresa: dict[str, list[tuple[int, Candidata]]] = defaultdict(list)

    def adicionar(self, vaga_id: int, c: Candidata) -> None:
        if c.url:
            self._por_url.setdefault(normalizar_url(c.url), vaga_id)
        if c.hash:
            self._por_hash.setdefault(c.hash, vaga_id)
        if chave := _empresa(c.empresa):
            self._por_empresa[chave].append((vaga_id, c))

    def procurar(self, c: Candidata) -> int | None:
        if c.url and (achada := self._por_url.get(normalizar_url(c.url))):
            return achada
        if c.hash and (achada := self._por_hash.get(c.hash)):
            return achada
        for vaga_id, conhecida in self._por_empresa.get(_empresa(c.empresa), []):
            if titulo_parecido(c.titulo, conhecida.titulo) and local_compativel(
                c.local, conhecida.local
            ):
                return vaga_id
        return None
