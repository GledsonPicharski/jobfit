"""Greenhouse: API pública por empresa (decisão 0009).

A lista da empresa vem sem o texto; o texto completo só é buscado para as vagas cujo
título passa na busca, pela mesma leitura usada para um link colado.
"""

from urllib.parse import urlsplit

import httpx2

from app.vagas.buscas import titulo_casa
from app.vagas.leitura import _GREENHOUSE, ErroLeituraVaga, VagaBruta, _greenhouse
from app.vagas.portais import Consulta, ErroPortal, data_iso, existe, obter_json

API = "https://boards-api.greenhouse.io/v1/boards"
_HOSTS = ("boards.greenhouse.io", "job-boards.greenhouse.io")


def _url_da_vaga(quadro: str, job: dict) -> str:
    """O link do próprio Greenhouse, que o `ler_url` e o `ainda_aberta` reconhecem."""
    url = job.get("absolute_url") or ""
    partes = urlsplit(url)
    if partes.hostname in _HOSTS and _GREENHOUSE.match(partes.path):
        return url
    return f"https://job-boards.greenhouse.io/{quadro}/jobs/{job['id']}"


def buscar(consulta: Consulta, cliente: httpx2.Client) -> list[VagaBruta]:
    vagas = []
    for empresa in consulta.empresas_do("greenhouse"):
        try:
            jobs = obter_json(cliente, f"{API}/{empresa.quadro}/jobs").get("jobs", [])
        except ErroPortal as erro:
            consulta.avisos.append(f"{empresa.nome}: {erro}")
            continue
        for job in jobs:
            if not titulo_casa(job.get("title"), consulta.titulos):
                continue
            consulta.pausar()
            url = _url_da_vaga(empresa.quadro, job)
            try:
                vaga = _greenhouse(cliente, empresa.quadro, str(job["id"]), url)
            except ErroLeituraVaga as erro:
                consulta.avisos.append(f"{empresa.nome} — {job.get('title')}: {erro}")
                continue
            vaga.estruturado.setdefault("empresa", empresa.nome)
            if publicada := data_iso(job.get("first_published") or job.get("updated_at")):
                vaga.estruturado["publicada_em"] = publicada
            vagas.append(vaga)
        consulta.pausar()
    return vagas


def ainda_aberta(url: str, cliente: httpx2.Client) -> bool:
    partes = urlsplit(url)
    m = _GREENHOUSE.match(partes.path) if partes.hostname in _HOSTS else None
    if m is None:
        return True  # sem como conferir: não marca como encerrada
    return existe(cliente, f"{API}/{m.group(1)}/jobs/{m.group(2)}")
