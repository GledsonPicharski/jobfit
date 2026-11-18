"""Leitores de portais: um arquivo por portal, todos com a mesma interface (decisão 0009).

    buscar(consulta, cliente) -> list[VagaBruta]
    ainda_aberta(url, cliente) -> bool

Os leitores só leem: filtram pelo título em código e devolvem a vaga como veio. Quem
deduplica, filtra e grava é o scanner. Um erro numa empresa vira aviso e não para as outras;
um erro no portal inteiro sobe como `ErroPortal`, e o scanner segue para o próximo portal.
"""

import html
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx2

from app.vagas.catalogo import Empresa
from app.vagas.leitura import VagaBruta, html_para_texto, limpar_texto


class ErroPortal(Exception):
    pass


@dataclass
class Consulta:
    titulos: list[str]
    empresas: list[Empresa] = field(default_factory=list)  # leitores por empresa (ATS)
    pausa: float = 0.0  # segundos entre requisições ao mesmo portal
    avisos: list[str] = field(default_factory=list)

    def empresas_do(self, ats: str) -> list[Empresa]:
        return [e for e in self.empresas if e.ats == ats]

    def pausar(self) -> None:
        if self.pausa:
            time.sleep(self.pausa)


def obter(cliente: httpx2.Client, url: str) -> httpx2.Response:
    try:
        resposta = cliente.get(url)
    except httpx2.HTTPError as erro:
        raise ErroPortal(f"sem resposta ({type(erro).__name__})") from erro
    if resposta.status_code >= 400:
        raise ErroPortal(f"respondeu com erro {resposta.status_code}")
    return resposta


def obter_json(cliente: httpx2.Client, url: str) -> Any:
    try:
        return obter(cliente, url).json()
    except ValueError as erro:
        raise ErroPortal("a resposta não veio no formato esperado") from erro


def existe(cliente: httpx2.Client, url: str) -> bool:
    """False só quando o portal diz que a vaga não existe mais (404 ou 410)."""
    try:
        resposta = cliente.get(url)
    except httpx2.HTTPError as erro:
        raise ErroPortal(f"sem resposta ({type(erro).__name__})") from erro
    if resposta.status_code in (404, 410):
        return False
    if resposta.status_code >= 400:
        raise ErroPortal(f"respondeu com erro {resposta.status_code}")
    return True


def data_iso(valor: Any) -> str | None:
    """Data de publicação como ISO: aceita texto ISO, RFC 822 (RSS) ou segundos ou
    milissegundos desde 1970. Sem fuso, vale UTC."""
    if valor in (None, ""):
        return None
    if isinstance(valor, int | float):
        segundos = valor / 1000 if valor > 1e11 else valor
        return datetime.fromtimestamp(segundos, UTC).isoformat()
    texto = str(valor).strip()
    try:
        data = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        try:
            data = parsedate_to_datetime(texto)
        except (TypeError, ValueError):
            return None
    return (data if data.tzinfo else data.replace(tzinfo=UTC)).isoformat()


def texto_de_html(*partes: str | None) -> str:
    return "\n\n".join(html_para_texto(html.unescape(p)) for p in partes if p)


# --- empresas dos ATS -------------------------------------------------------------

_LISTA_DO_ATS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs",
    "lever": "https://api.lever.co/v0/postings/{}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{}",
}
_QUADRO_NA_URL = [
    ("greenhouse", re.compile(r"greenhouse\.io/(?:v1/boards/|embed/job_board\?for=)?([\w.-]+)")),
    ("lever", re.compile(r"lever\.co/(?:v0/postings/)?([\w.-]+)")),
    ("ashby", re.compile(r"ashbyhq\.com/(?:posting-api/job-board/)?([\w.-]+)")),
]


def ler_quadro(texto: str) -> tuple[str | None, str]:
    """O ATS e o identificador do quadro a partir do link colado (ou o próprio identificador)."""
    texto = texto.strip()
    for ats, padrao in _QUADRO_NA_URL:
        if m := padrao.search(texto):
            return ats, m.group(1)
    return None, texto.strip("/")


def conferir_quadro(ats: str, quadro: str, cliente: httpx2.Client) -> int:
    """Quantas vagas o quadro tem agora; `ErroPortal` se o quadro não existe."""
    try:
        dados = obter_json(cliente, _LISTA_DO_ATS[ats].format(quadro))
    except ErroPortal as erro:
        raise ErroPortal(f"não achei o quadro {quadro!r} no {ats.capitalize()} ({erro})") from erro
    vagas = dados if isinstance(dados, list) else dados.get("jobs")
    if not isinstance(vagas, list):
        raise ErroPortal(f"não achei o quadro {quadro!r} no {ats.capitalize()}")
    return len(vagas)


_LOCAL_MAXIMO = 80


def montar(
    texto: str,
    fonte: str,
    url: str,
    *,
    titulo: str | None,
    empresa: str | None,
    local: str | None = None,
    modalidade: str | None = None,
    publicada_em: Any = None,
    restricoes: list[str] | None = None,
) -> VagaBruta:
    if local and len(local) > _LOCAL_MAXIMO:  # há vaga "remota" com 200 países listados
        local = local[: _LOCAL_MAXIMO - 1].rsplit(",", 1)[0] + "…"
    estruturado = {
        "titulo": titulo,
        "empresa": empresa,
        "local": local,
        "modalidade": modalidade,
        "publicada_em": data_iso(publicada_em),
        "restricoes": [r for r in restricoes or [] if r],
    }
    return VagaBruta(limpar_texto(texto), fonte, url, {k: v for k, v in estruturado.items() if v})
