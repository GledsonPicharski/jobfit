"""Ashby: API pública por empresa; a lista já traz o texto e, às vezes, o salário."""

import re
from urllib.parse import urlsplit

import httpx2

from app.vagas.buscas import titulo_casa
from app.vagas.leitura import VagaBruta
from app.vagas.portais import Consulta, ErroPortal, montar, obter_json

API = "https://api.ashbyhq.com/posting-api/job-board"
_MODALIDADE = {"remote": "remoto", "hybrid": "hibrido", "onsite": "presencial"}
_URL = re.compile(r"^/([^/]+)/([0-9a-f-]{36})")


def _modalidade(job: dict) -> str | None:
    tipo = (job.get("workplaceType") or "").casefold().replace("-", "")
    return _MODALIDADE.get(tipo) or ("remoto" if job.get("isRemote") else None)


def _vaga(job: dict, empresa: str) -> VagaBruta:
    locais = [job.get("location")] + [
        s.get("location") for s in job.get("secondaryLocations") or []
    ]
    partes = [job.get("title", ""), job.get("descriptionPlain", "")]
    if resumo := (job.get("compensation") or {}).get("compensationTierSummary"):
        partes.append(f"Remuneração: {resumo}")
    modalidade = _modalidade(job)
    return montar(
        "\n\n".join(p for p in partes if p),
        "ashby",
        job["jobUrl"],
        titulo=job.get("title"),
        empresa=empresa,
        local=job.get("location"),
        modalidade=modalidade,
        publicada_em=job.get("publishedAt"),
        restricoes=locais if modalidade == "remoto" else None,
    )


def _jobs(cliente: httpx2.Client, quadro: str) -> list[dict]:
    dados = obter_json(cliente, f"{API}/{quadro}?includeCompensation=true")
    return [j for j in dados.get("jobs", []) if j.get("isListed", True)]


def buscar(consulta: Consulta, cliente: httpx2.Client) -> list[VagaBruta]:
    vagas = []
    for empresa in consulta.empresas_do("ashby"):
        try:
            jobs = _jobs(cliente, empresa.quadro)
        except ErroPortal as erro:
            consulta.avisos.append(f"{empresa.nome}: {erro}")
            continue
        vagas += [
            _vaga(j, empresa.nome) for j in jobs if titulo_casa(j.get("title"), consulta.titulos)
        ]
        consulta.pausar()
    return vagas


def ainda_aberta(url: str, cliente: httpx2.Client) -> bool:
    """O Ashby não tem consulta por vaga: a vaga continua aberta se ainda está na lista."""
    partes = urlsplit(url)
    m = _URL.match(partes.path) if partes.hostname == "jobs.ashbyhq.com" else None
    if m is None:
        return True
    return any(j.get("id") == m.group(2) for j in _jobs(cliente, m.group(1)))
