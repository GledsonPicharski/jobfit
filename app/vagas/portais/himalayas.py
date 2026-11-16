"""Himalayas: API pública de vagas remotas, com busca por termo e países aceitos."""

from urllib.parse import quote

import httpx2

from app.vagas.buscas import titulo_casa
from app.vagas.leitura import VagaBruta
from app.vagas.portais import Consulta, existe, montar, obter_json, texto_de_html

API = "https://himalayas.app/jobs/api/search"
POR_TERMO = 20


def _vaga(job: dict) -> VagaBruta:
    partes = [job.get("title", ""), texto_de_html(job.get("description"))]
    if job.get("minSalary") and job.get("currency"):
        periodo = {"year": "por ano", "month": "por mês"}.get(job.get("salaryPeriod") or "", "")
        teto = f" - {job['maxSalary']}" if job.get("maxSalary") else ""
        partes.append(f"Salário: {job['currency']} {job['minSalary']}{teto} {periodo}".strip())
    restricoes = job.get("locationRestrictions") or []
    return montar(
        "\n\n".join(partes),
        "himalayas",
        job.get("guid") or job["applicationLink"],
        titulo=job.get("title"),
        empresa=job.get("companyName"),
        local=", ".join(restricoes) or "Worldwide",
        modalidade="remoto",
        publicada_em=job.get("pubDate"),
        restricoes=restricoes,
    )


def buscar(consulta: Consulta, cliente: httpx2.Client) -> list[VagaBruta]:
    vagas: dict[str, VagaBruta] = {}
    for termo in consulta.titulos:
        dados = obter_json(cliente, f"{API}?q={quote(termo)}&limit={POR_TERMO}")
        for job in dados.get("jobs", []):
            if titulo_casa(job.get("title"), consulta.titulos):
                vaga = _vaga(job)
                vagas.setdefault(vaga.url, vaga)
        consulta.pausar()
    return list(vagas.values())


def ainda_aberta(url: str, cliente: httpx2.Client) -> bool:
    return existe(cliente, url)
