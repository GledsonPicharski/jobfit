"""Remotive: API pública (decisão 0009).

Os termos pedem link para a vaga na Remotive, a Remotive citada como fonte e no máximo
4 consultas por dia. Por isso o leitor faz uma consulta só por rodada, sem termo de busca,
filtra o título em código, e o scanner respeita 6 horas entre rodadas (`config/scanner.yaml`).
"""

import httpx2

from app.vagas.buscas import titulo_casa
from app.vagas.leitura import VagaBruta
from app.vagas.portais import Consulta, existe, montar, obter_json, texto_de_html

API = "https://remotive.com/api/remote-jobs"


def buscar(consulta: Consulta, cliente: httpx2.Client) -> list[VagaBruta]:
    vagas = []
    for job in obter_json(cliente, API).get("jobs", []):
        if not titulo_casa(job.get("title"), consulta.titulos):
            continue
        partes = [job.get("title", ""), texto_de_html(job.get("description"))]
        if salario := job.get("salary"):
            partes.append(f"Salário: {salario}")
        local = job.get("candidate_required_location") or ""
        vagas.append(
            montar(
                "\n\n".join(partes),
                "remotive",
                job["url"],
                titulo=job.get("title"),
                empresa=(job.get("company_name") or "").strip(),
                local=local or None,
                modalidade="remoto",
                publicada_em=job.get("publication_date"),
                restricoes=[r.strip() for r in local.split(",")],
            )
        )
    return vagas


def ainda_aberta(url: str, cliente: httpx2.Client) -> bool:
    return existe(cliente, url)
