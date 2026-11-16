"""Lever: API pública por empresa; a lista já traz o texto completo (decisão 0009)."""

from urllib.parse import urlsplit

import httpx2

from app.vagas.buscas import titulo_casa
from app.vagas.leitura import _LEVER, VagaBruta, vaga_lever
from app.vagas.portais import Consulta, ErroPortal, data_iso, existe, obter_json

API = "https://api.lever.co/v0/postings"


def buscar(consulta: Consulta, cliente: httpx2.Client) -> list[VagaBruta]:
    vagas = []
    for empresa in consulta.empresas_do("lever"):
        try:
            jobs = obter_json(cliente, f"{API}/{empresa.quadro}?mode=json")
        except ErroPortal as erro:
            consulta.avisos.append(f"{empresa.nome}: {erro}")
            continue
        for job in jobs if isinstance(jobs, list) else []:
            if not titulo_casa(job.get("text"), consulta.titulos):
                continue
            url = job.get("hostedUrl") or f"https://jobs.lever.co/{empresa.quadro}/{job['id']}"
            vaga = vaga_lever(job, url)
            vaga.fonte = "lever"
            vaga.estruturado["empresa"] = empresa.nome
            categorias = job.get("categories") or {}
            if publicada := data_iso(job.get("createdAt")):
                vaga.estruturado["publicada_em"] = publicada
            if vaga.estruturado.get("modalidade") == "remoto":
                vaga.estruturado["restricoes"] = categorias.get("allLocations") or [
                    categorias.get("location")
                ]
            vagas.append(vaga)
        consulta.pausar()
    return vagas


def ainda_aberta(url: str, cliente: httpx2.Client) -> bool:
    partes = urlsplit(url)
    m = _LEVER.match(partes.path) if partes.hostname == "jobs.lever.co" else None
    if m is None:
        return True
    return existe(cliente, f"{API}/{m.group(1)}/{m.group(2)}")
