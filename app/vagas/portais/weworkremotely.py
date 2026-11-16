"""We Work Remotely: RSS público com as vagas mais recentes de todas as categorias.

O título do item vem como "Empresa: Cargo"; a região diz de onde a vaga aceita gente.
"""

import re
import xml.etree.ElementTree as ET

import httpx2

from app.vagas.buscas import titulo_casa
from app.vagas.leitura import VagaBruta
from app.vagas.portais import Consulta, ErroPortal, existe, montar, obter, texto_de_html

FEED = "https://weworkremotely.com/remote-jobs.rss"
_BANDEIRA = re.compile("^[\U0001f1e6-\U0001f1ff\\s]+")  # "🇨🇦 Canada" vira "Canada"


def _item(item: ET.Element) -> VagaBruta | None:
    def campo(nome: str) -> str:
        return (item.findtext(nome) or "").strip()

    empresa, _, titulo = campo("title").partition(": ")
    if not titulo:
        empresa, titulo = "", empresa
    link = campo("link") or campo("guid")
    if not link:
        return None
    lugares = [campo("region"), _BANDEIRA.sub("", campo("country"))]
    restricoes = [lugar for lugar in lugares if lugar]
    return montar(
        "\n\n".join([titulo, texto_de_html(campo("description"))]),
        "weworkremotely",
        link,
        titulo=titulo,
        empresa=empresa or None,
        local=restricoes[0] if restricoes else None,
        modalidade="remoto",
        publicada_em=campo("pubDate"),
        restricoes=restricoes,
    )


def buscar(consulta: Consulta, cliente: httpx2.Client) -> list[VagaBruta]:
    try:
        raiz = ET.fromstring(obter(cliente, FEED).content)
    except ET.ParseError as erro:
        raise ErroPortal("o feed não veio no formato esperado") from erro
    vagas = []
    for item in raiz.iter("item"):
        titulo = (item.findtext("title") or "").partition(": ")[2]
        if titulo_casa(titulo, consulta.titulos) and (vaga := _item(item)):
            vagas.append(vaga)
    return vagas


def ainda_aberta(url: str, cliente: httpx2.Client) -> bool:
    return existe(cliente, url)
