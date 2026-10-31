"""O que dá para saber de uma vaga sem IA: modalidade, local, senioridade, idioma, salário.

Serve aos filtros duros, que rodam antes de qualquer token (regra 1). Quando a página
traz dados estruturados (API do ATS ou JSON-LD), eles prevalecem sobre o regex. Dado que
não se acha fica `None`, e dado ausente nunca bloqueia uma vaga.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from app.dossie.modelos import Fato, sem_acento

Modalidade = Literal["remoto", "hibrido", "presencial"]
Senioridade = Literal["estagio", "junior", "pleno", "senior", "especialista", "gestao", "diretoria"]

MODALIDADES: dict[str, str] = {"remoto": "Remoto", "hibrido": "Híbrido", "presencial": "Presencial"}
SENIORIDADES: dict[str, str] = {
    "estagio": "Estágio",
    "junior": "Júnior",
    "pleno": "Pleno",
    "senior": "Sênior",
    "especialista": "Especialista",
    "gestao": "Gestão (coordenação, gerência, head)",
    "diretoria": "Diretoria",
}
NIVEIS_INGLES = {1: "básico", 2: "intermediário", 3: "avançado", 4: "fluente"}


def _normal(texto: str) -> str:
    return sem_acento(texto).casefold()


# --- modalidade -----------------------------------------------------------------

_ROTULO_MODALIDADE = re.compile(
    r"(modelo de trabalho|modalidade|regime de trabalho|formato de trabalho|workplace type"
    r"|work model|location type)\s*[:\-–]\s*([\w-]+)"
)
_PALAVRA_MODALIDADE = {
    "remoto": "remoto",
    "remote": "remoto",
    "home": "remoto",
    "hibrido": "hibrido",
    "hybrid": "hibrido",
    "presencial": "presencial",
    "on-site": "presencial",
    "onsite": "presencial",
    "office": "presencial",
}
_HIBRIDO = re.compile(r"\b(hibrido|hybrid)\b")
_REMOTO = re.compile(r"\b(remoto|remota|remote|home office|anywhere|teletrabalho)\b")
_PRESENCIAL = re.compile(r"\b(presencial|on-site|onsite|in-office|in office)\b")


def modalidade(texto: str) -> Modalidade | None:
    normal = _normal(texto)
    rotulo = _ROTULO_MODALIDADE.search(normal)
    if rotulo and (achada := _PALAVRA_MODALIDADE.get(rotulo.group(2))):
        return achada  # type: ignore[return-value]
    if _HIBRIDO.search(normal):
        return "hibrido"
    remoto, presencial = bool(_REMOTO.search(normal)), bool(_PRESENCIAL.search(normal))
    if remoto != presencial:
        return "remoto" if remoto else "presencial"
    return None  # nada dito, ou as duas coisas: melhor não adivinhar


# --- senioridade ----------------------------------------------------------------

_SENIORIDADE: list[tuple[Senioridade, re.Pattern]] = [
    (
        "diretoria",
        re.compile(r"\b(diretor|diretora|director|vp|vice[- ]president|cto|cdo|chief)\b"),
    ),
    ("gestao", re.compile(r"\b(coordenador|coordenadora|gerente|manager|head|lider|supervisor)\b")),
    ("especialista", re.compile(r"\b(especialista|staff|principal|specialist|expert)\b")),
    ("senior", re.compile(r"\b(senior|sr)\b")),
    ("pleno", re.compile(r"\b(pleno|pl|mid[- ]level)\b")),
    ("junior", re.compile(r"\b(junior|jr)\b")),
    ("estagio", re.compile(r"\b(estagio|estagiario|estagiaria|intern|internship|trainee)\b")),
]


def senioridade(titulo: str) -> Senioridade | None:
    normal = _normal(titulo)
    return next((nivel for nivel, padrao in _SENIORIDADE if padrao.search(normal)), None)


# --- idioma ---------------------------------------------------------------------

_PALAVRAS_EN = {"the", "and", "with", "our", "you", "will", "for", "are", "to", "of", "we"}
_PALAVRAS_PT = {"de", "e", "com", "para", "que", "uma", "um", "em", "nossa", "voce", "os", "as"}


def idioma_do_texto(texto: str) -> Literal["pt", "en"]:
    palavras = re.findall(r"[a-z]+", _normal(texto))
    en = sum(p in _PALAVRAS_EN for p in palavras)
    pt = sum(p in _PALAVRAS_PT for p in palavras)
    return "en" if en > pt else "pt"


_NIVEL_PALAVRA = [
    (
        4,
        (
            "fluente",
            "fluent",
            "fluencia",
            "fluency",
            "nativ",
            "bilingu",
            "full professional",
            "c2",
            "c1",
        ),
    ),
    (3, ("avancad", "advanced", "profissional", "professional", "proficient", "business", "b2")),
    (2, ("intermediar", "intermediate", "limited", "b1")),
    (1, ("basic", "elementary", "a1", "a2")),
]
_INGLES_PT = re.compile(r"ingles\s+(?:nivel\s+)?(\w+)|(fluencia)\s+(?:em|no)\s+ingles")
_INGLES_EN = re.compile(
    r"\b(fluent|advanced|intermediate|basic|proficient|business)[- ](?:level\s+)?english"
    r"|english\s+(fluency|proficiency)"
)


def _nivel(texto: str) -> int | None:
    return next((n for n, palavras in _NIVEL_PALAVRA if any(p in texto for p in palavras)), None)


def ingles_exigido(texto: str) -> int | None:
    """1 básico, 2 intermediário, 3 avançado, 4 fluente; vaga em inglês exige ao menos 3."""
    normal = _normal(texto)
    niveis = [
        _nivel(next(g for g in m.groups() if g))
        for m in [*_INGLES_PT.finditer(normal), *_INGLES_EN.finditer(normal)]
    ]
    if achados := [n for n in niveis if n]:
        return max(achados)
    return 3 if idioma_do_texto(texto) == "en" else None


def nivel_ingles_declarado(fatos: list[Fato]) -> int | None:
    """O nível de inglês que o dossiê declara, nos fatos `idioma`."""
    niveis = [
        _nivel(_normal(f.texto))
        for f in fatos
        if f.tipo == "idioma" and re.search(r"\b(ingles|english)\b", _normal(f.texto))
    ]
    return max((n for n in niveis if n), default=None)


# --- salário --------------------------------------------------------------------


@dataclass(frozen=True)
class Salario:
    moeda: Literal["BRL", "USD"]
    minimo: Decimal  # por mês
    maximo: Decimal


_MOEDA = r"(R\$|US\$|USD|\$)"
_VALOR = r"(\d[\d.,]*)\s*(k|mil)?"
_SALARIO = re.compile(
    rf"{_MOEDA}\s*{_VALOR}(?:\s*(?:-|–|a|ate|to)\s*{_MOEDA}?\s*{_VALOR})?", re.IGNORECASE
)
_ANUAL = re.compile(r"(por ano|/\s*ano|anual|per year|/\s*year|annual|a year|yearly)")


def _numero(texto: str, moeda: str, multiplicador: str | None) -> Decimal | None:
    bruto = texto.rstrip(".,")
    bruto = bruto.replace(",", "") if moeda == "USD" else bruto.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(bruto)
    except InvalidOperation:
        return None
    return valor * 1000 if multiplicador else valor


def ler_salario(texto: str) -> Salario | None:
    for m in _SALARIO.finditer(sem_acento(texto)):
        simbolo, valor1, mult1, _, valor2, mult2 = m.groups()
        moeda = "BRL" if simbolo.upper() == "R$" else "USD"
        minimo = _numero(valor1, moeda, mult1 or mult2)
        maximo = _numero(valor2, moeda, mult2) if valor2 else minimo
        if minimo is None or maximo is None or minimo < 100:
            continue
        depois = _normal(texto[m.end() : m.end() + 40])
        if _ANUAL.search(depois):
            minimo, maximo = minimo / 12, maximo / 12
        return Salario(moeda, minimo.quantize(Decimal(1)), maximo.quantize(Decimal(1)))
    return None


# --- tudo junto -----------------------------------------------------------------

_LOCAL = re.compile(
    r"^\s*(?:local|localizacao|location|cidade)\s*:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE
)


@dataclass(frozen=True)
class Metadados:
    titulo: str | None = None
    empresa: str | None = None
    local: str | None = None
    modalidade: Modalidade | None = None
    senioridade: Senioridade | None = None
    idioma: str = "pt"
    ingles: int | None = None
    salario: Salario | None = None


def _local(texto: str) -> str | None:
    for linha in texto.splitlines():
        if m := _LOCAL.match(sem_acento(linha)):
            return linha[m.start(1) :].strip()[:80] or None  # o original, com acento
    return None


def extrair_metadados(texto: str, estruturado: dict[str, Any] | None = None) -> Metadados:
    dados = estruturado or {}
    primeira = next((linha.strip() for linha in texto.splitlines() if linha.strip()), "")
    titulo = dados.get("titulo") or (primeira if len(primeira) <= 120 else None)
    return Metadados(
        titulo=titulo,
        empresa=dados.get("empresa"),
        local=dados.get("local") or _local(texto),
        modalidade=dados.get("modalidade") or modalidade(texto),
        senioridade=senioridade(titulo) if titulo else None,
        idioma=idioma_do_texto(texto),
        ingles=ingles_exigido(texto),
        salario=ler_salario(texto),
    )
