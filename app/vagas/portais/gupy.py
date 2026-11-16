"""Gupy: a busca pública do portal de vagas (decisão 0009).

O endpoint é o mesmo que a página de busca usa, sem documentação: se mudar, o leitor sobe
`ErroPortal` e as vagas da Gupy continuam entrando por link colado. Poucas requisições por
rodada: uma por título buscado.
"""

from urllib.parse import quote, urlsplit

import httpx2

from app.vagas.buscas import titulo_casa
from app.vagas.leitura import VagaBruta
from app.vagas.portais import Consulta, ErroPortal, montar, obter_json, texto_de_html

API = "https://portal.gupy.io/api/job-search/jobs"
POR_TERMO = 20
_MODALIDADE = {"remote": "remoto", "hybrid": "hibrido", "on-site": "presencial"}
_CONTRATACAO = {
    "vacancy_type_effective": "CLT",
    "vacancy_legal_entity": "PJ",
    "vacancy_type_internship": "Estágio",
    "vacancy_type_temporary": "Temporário",
    "vacancy_type_apprentice": "Jovem aprendiz",
}


def _url(job: dict) -> str:
    """O link clássico da vaga, sem o código de rastreio: `<empresa>.gupy.io/jobs/<id>`."""
    host = urlsplit(job.get("jobUrl") or job.get("careerPageUrl") or "").hostname
    if not host or not host.endswith(".gupy.io"):
        raise ErroPortal("a vaga veio sem o endereço da empresa na Gupy")
    return f"https://{host}/jobs/{job['id']}"


def _vaga(job: dict) -> VagaBruta:
    partes = [job.get("name", "").strip(), texto_de_html(job.get("description"))]
    if contratacao := _CONTRATACAO.get(job.get("type") or ""):
        partes.append(f"Contratação: {contratacao}")
    local = " - ".join(p for p in (job.get("city"), job.get("state")) if p)
    return montar(
        "\n\n".join(partes),
        "gupy",
        _url(job),
        titulo=job.get("name", "").strip(),
        empresa=job.get("careerPageName"),
        local=local or None,
        modalidade=_MODALIDADE.get(job.get("workplaceType") or ""),
        publicada_em=job.get("publishedDate"),
        restricoes=["Brasil"] if job.get("workplaceType") == "remote" else None,
    )


def buscar(consulta: Consulta, cliente: httpx2.Client) -> list[VagaBruta]:
    vagas: dict[str, VagaBruta] = {}
    for termo in consulta.titulos:
        url = f"{API}?jobName={quote(termo)}&limit={POR_TERMO}&offset=0"
        for job in obter_json(cliente, url).get("data", []):
            if not titulo_casa(job.get("name"), consulta.titulos):
                continue
            try:
                vaga = _vaga(job)
            except ErroPortal as erro:
                consulta.avisos.append(f"{job.get('name')}: {erro}")
                continue
            vagas.setdefault(vaga.url, vaga)
        consulta.pausar()
    return list(vagas.values())


def ainda_aberta(url: str, cliente: httpx2.Client) -> bool:
    """Aberta: a página da vaga responde com os dados dela. Encerrada: 404, 410 ou a Gupy
    manda para o login (o que ela faz com vaga que não existe mais)."""
    try:
        resposta = cliente.get(url, follow_redirects=False)
    except httpx2.HTTPError as erro:
        raise ErroPortal(f"sem resposta ({type(erro).__name__})") from erro
    if resposta.status_code in (404, 410) or resposta.is_redirect:
        return False
    if resposta.status_code >= 400:
        raise ErroPortal(f"respondeu com erro {resposta.status_code}")
    return "JobPosting" in resposta.text
