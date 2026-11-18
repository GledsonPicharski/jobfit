"""Get on Board: API pública de vagas da América Latina, com busca por termo.

O `robots.txt` declara `ai-train=no`: o texto só vai para a IA quando a pessoa escolhe
avaliar a vaga, como uma vaga colada (decisão 0009).
"""

import json
from urllib.parse import quote

import httpx2

from app.vagas.buscas import titulo_casa
from app.vagas.leitura import VagaBruta
from app.vagas.portais import Consulta, existe, montar, obter_json, texto_de_html

API = "https://www.getonbrd.com/api/v0"
POR_TERMO = 20
_MODALIDADE = {
    "fully_remote": "remoto",
    "remote_local": "remoto",
    "temporarily_remote": "hibrido",
    "hybrid": "hibrido",
    "no_remote": "presencial",
}


def _vaga(dados: dict) -> VagaBruta:
    a = dados["attributes"]
    empresa = (((a.get("company") or {}).get("data") or {}).get("attributes") or {}).get("name")
    partes = [
        a.get("title", ""),
        texto_de_html(
            a.get("description"), a.get("functions"), a.get("desirable"), a.get("benefits")
        ),
    ]
    if a.get("min_salary") or a.get("max_salary"):
        faixa = " - ".join(f"US$ {v}" for v in (a.get("min_salary"), a.get("max_salary")) if v)
        partes.append(f"Salário: {faixa} por mês")
    modalidade = _MODALIDADE.get(a.get("remote_modality") or "")
    paises = a.get("countries") or []
    url = (dados.get("links") or {}).get(
        "public_url"
    ) or f"https://www.getonbrd.com/jobs/{dados['id']}"
    return montar(
        "\n\n".join(partes),
        "getonboard",
        url,
        titulo=a.get("title"),
        empresa=empresa,
        local=", ".join(paises) or None,
        modalidade=modalidade,
        publicada_em=a.get("published_at"),
        restricoes=paises if modalidade == "remoto" else None,
    )


def buscar(consulta: Consulta, cliente: httpx2.Client) -> list[VagaBruta]:
    expandir = quote(json.dumps(["company"]))
    vagas: dict[str, VagaBruta] = {}
    for termo in consulta.titulos:
        url = f"{API}/search/jobs?query={quote(termo)}&per_page={POR_TERMO}&expand={expandir}"
        for dados in obter_json(cliente, url).get("data", []):
            if titulo_casa(dados.get("attributes", {}).get("title"), consulta.titulos):
                vaga = _vaga(dados)
                vagas.setdefault(vaga.url, vaga)
        consulta.pausar()
    return list(vagas.values())


def ainda_aberta(url: str, cliente: httpx2.Client) -> bool:
    """A página pública: redireciona para o endereço com a categoria se a vaga existe,
    404 se não existe (a API de uma vaga só pede login)."""
    return existe(cliente, url)
