"""Ler uma vaga a partir de uma URL ou de texto colado (regra 1: código, sem IA).

Ordem para URL: API pública do ATS (Greenhouse, Lever) → JSON-LD `JobPosting` da página
(Gupy e a maioria dos sites) → texto principal da página. LinkedIn não é lido (regra 7):
a pessoa cola o texto. O texto da vaga é dado não confiável (regra 8) e é guardado como
veio, para continuar legível mesmo se a vaga sair do ar.
"""

import html
import ipaddress
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx2

LIMITE_BYTES = 2 * 1024 * 1024
MINIMO_CARACTERES = 200
USER_AGENT = "JobFit/0.1 (app local de carreira; https://github.com/GledsonPicharski/jobfit)"

_RASTREIO = re.compile(r"^(utm_.*|gh_src|ref|source|trk|lever-source.*|src)$", re.IGNORECASE)
_GREENHOUSE = re.compile(r"^/([^/]+)/jobs/(\d+)")
_LEVER = re.compile(r"^/([^/]+)/([0-9a-f-]{36})")
_MODALIDADE_LEVER = {"remote": "remoto", "hybrid": "hibrido", "onsite": "presencial"}
_FIM_DE_BLOCO = re.compile(r"(</(?:p|li|h[1-6]|div|tr|ul|ol|section)>|<br\s*/?>)", re.IGNORECASE)


class ErroLeituraVaga(ValueError):
    pass


@dataclass
class VagaBruta:
    texto: str
    fonte: str  # greenhouse | lever | gupy | pagina | texto
    url: str | None = None
    estruturado: dict[str, Any] = field(default_factory=dict)


# --- texto ----------------------------------------------------------------------


def limpar_texto(texto: str) -> str:
    linhas = [re.sub(r"[ \t\xa0]+", " ", linha).strip() for linha in texto.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()


def html_para_texto(conteudo: str, principal: bool = False) -> str:
    """Texto legível do HTML: um bloco por linha, itens de lista com "- "."""
    from selectolax.lexbor import LexborHTMLParser

    conteudo = _FIM_DE_BLOCO.sub(r"\1\n", conteudo)
    conteudo = re.sub(r"<li(\s[^>]*)?>", r"<li\1>- ", conteudo, flags=re.IGNORECASE)
    arvore = LexborHTMLParser(conteudo)
    arvore.strip_tags(["script", "style", "noscript", "svg", "nav", "header", "footer", "form"])
    raiz = (arvore.css_first("main") or arvore.css_first("article")) if principal else None
    raiz = raiz or arvore.body or arvore.root
    return limpar_texto(raiz.text(separator="") if raiz else "")


def ler_texto(texto: str) -> VagaBruta:
    limpo = limpar_texto(texto.replace("\r\n", "\n"))
    if not limpo:
        raise ErroLeituraVaga("Cole o texto ou a URL da vaga.")
    return VagaBruta(texto=limpo, fonte="texto")


# --- URL ------------------------------------------------------------------------


def normalizar_url(url: str) -> str:
    """Sem rastreio, fragmento e barra final: a mesma vaga dá sempre a mesma URL."""
    partes = urlsplit(url.strip())
    consulta = [(k, v) for k, v in parse_qsl(partes.query) if not _RASTREIO.match(k)]
    caminho = partes.path.rstrip("/") if partes.path not in ("", "/") else ""
    return urlunsplit(
        (partes.scheme.lower(), partes.netloc.lower(), caminho, urlencode(consulta), "")
    )


def _validar(url: str) -> str:
    if "://" not in url:
        url = "https://" + url.strip()
    partes = urlsplit(url)
    host = (partes.hostname or "").lower()
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        raise ErroLeituraVaga(
            "O JobFit não lê páginas do LinkedIn. Abra a vaga, copie a descrição "
            "e cole o texto aqui."
        )
    if partes.scheme not in ("http", "https") or "." not in host or host == "localhost":
        raise ErroLeituraVaga("Endereço inválido: use o link completo da vaga (https://…).")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip and (ip.is_private or ip.is_loopback or ip.is_link_local):
        raise ErroLeituraVaga("Endereço inválido: o JobFit só lê vagas na internet.")
    return normalizar_url(url)


def _buscar(cliente: httpx2.Client, url: str) -> httpx2.Response:
    try:
        resposta = cliente.get(url)
    except httpx2.HTTPError as erro:
        raise ErroLeituraVaga(
            "Não consegui abrir a página. Confira a internet ou cole o texto da vaga."
        ) from erro
    if resposta.status_code in (404, 410):
        raise ErroLeituraVaga("A vaga não foi encontrada: pode ter sido encerrada.")
    if resposta.status_code >= 400:
        raise ErroLeituraVaga(
            f"A página respondeu com erro ({resposta.status_code}). Cole o texto da vaga."
        )
    if len(resposta.content) > LIMITE_BYTES:
        raise ErroLeituraVaga("A página é grande demais para ser uma vaga. Cole o texto.")
    return resposta


def _greenhouse(cliente: httpx2.Client, quadro: str, vaga_id: str, url: str) -> VagaBruta:
    api = f"https://boards-api.greenhouse.io/v1/boards/{quadro}/jobs/{vaga_id}"
    dados = _buscar(cliente, api).json()
    estruturado = {
        "titulo": dados.get("title"),
        "empresa": dados.get("company_name"),
        "local": (dados.get("location") or {}).get("name"),
    }
    texto = html_para_texto(html.unescape(dados.get("content") or ""))
    return VagaBruta(
        f"{dados.get('title', '')}\n\n{texto}".strip(),
        "greenhouse",
        url,
        {k: v for k, v in estruturado.items() if v},
    )


def _lever(cliente: httpx2.Client, empresa: str, vaga_id: str, url: str) -> VagaBruta:
    dados = _buscar(cliente, f"https://api.lever.co/v0/postings/{empresa}/{vaga_id}").json()
    partes = [dados.get("text", ""), dados.get("descriptionPlain", "")]
    for lista in dados.get("lists") or []:
        partes += [lista.get("text", ""), html_para_texto(f"<ul>{lista.get('content', '')}</ul>")]
    partes.append(dados.get("additionalPlain", ""))
    estruturado = {
        "titulo": dados.get("text"),
        "local": (dados.get("categories") or {}).get("location"),
        "modalidade": _MODALIDADE_LEVER.get(dados.get("workplaceType") or ""),
    }
    texto = limpar_texto("\n\n".join(p for p in partes if p))
    return VagaBruta(texto, "lever", url, {k: v for k, v in estruturado.items() if v})


def _job_posting(pagina: str) -> dict[str, Any] | None:
    for bloco in re.findall(
        r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", pagina, re.DOTALL | re.IGNORECASE
    ):
        try:
            dados = json.loads(bloco)
        except json.JSONDecodeError:
            continue
        candidatos = dados if isinstance(dados, list) else dados.get("@graph", [dados])
        for item in candidatos:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return None


def _local_json_ld(posting: dict[str, Any]) -> str | None:
    locais = posting.get("jobLocation") or []
    for local in locais if isinstance(locais, list) else [locais]:
        endereco = (local or {}).get("address") or {}
        partes = [endereco.get("addressLocality"), endereco.get("addressRegion")]
        if any(partes):
            return ", ".join(p for p in partes if p)
    return None


def _pagina(cliente: httpx2.Client, url: str) -> VagaBruta:
    pagina = _buscar(cliente, url).text
    fonte = "gupy" if (urlsplit(url).hostname or "").endswith("gupy.io") else "pagina"
    if posting := _job_posting(pagina):
        titulo = posting.get("title")
        empresa = (posting.get("hiringOrganization") or {}).get("name")
        remoto = str(posting.get("jobLocationType", "")).upper() == "TELECOMMUTE"
        estruturado = {
            "titulo": titulo,
            "empresa": empresa,
            "local": _local_json_ld(posting),
            "modalidade": "remoto" if remoto else None,
        }
        descricao = html_para_texto(html.unescape(posting.get("description") or ""))
        texto = f"{titulo or ''}\n\n{descricao}".strip()
        if len(descricao) >= 50:
            return VagaBruta(texto, fonte, url, {k: v for k, v in estruturado.items() if v})
    texto = html_para_texto(pagina, principal=True)
    if len(texto) < MINIMO_CARACTERES:
        raise ErroLeituraVaga(
            "Não consegui ler a descrição nessa página (ela pode depender de login ou de "
            "JavaScript). Abra a vaga, copie a descrição e cole o texto aqui."
        )
    return VagaBruta(texto, fonte, url)


def novo_cliente() -> httpx2.Client:
    return httpx2.Client(timeout=15, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def ler_url(url: str, cliente: httpx2.Client | None = None) -> VagaBruta:
    url = _validar(url)
    partes = urlsplit(url)
    host = partes.hostname or ""
    with cliente or novo_cliente() as http:
        if host in ("boards.greenhouse.io", "job-boards.greenhouse.io") and (
            m := _GREENHOUSE.match(partes.path)
        ):
            return _greenhouse(http, m.group(1), m.group(2), url)
        if host == "jobs.lever.co" and (m := _LEVER.match(partes.path)):
            return _lever(http, m.group(1), m.group(2), url)
        return _pagina(http, url)
