"""Leitor, em código, do PDF do LinkedIn (Perfil → Recursos → Salvar como PDF).

O layout é previsível: uma barra lateral à esquerda (contato, competências, idiomas,
certificações, prêmios) e a coluna principal (nome, título, local, resumo, experiência,
formação). Tamanho e cor da letra dizem o que cada linha é. Cargos, empresas, datas e os
itens da lateral viram candidatos direto; só as descrições ficam para a IA.
"""

import html
import io
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from app.dossie.modelos import Periodo, sem_acento
from app.dossie.propostas import Candidato

FONTE = "linkedin_pdf"

# Tamanhos (pt) do PDF do LinkedIn, com folga para arredondamento.
_NOME = 20
_TITULO_SECAO = 14.5
_EMPRESA = 11.75
_CARGO = 11.25
_TITULO_LATERAL = 12.5
_RODAPE = 9.5
_LATERAL_ATE_X = 200
# Na lateral, item quebrado em duas linhas tem espaço menor que entre dois itens.
_QUEBRA_LATERAL = 15
# Na coluna principal, espaço maior que isto (em tamanhos da letra) abre parágrafo.
_PARAGRAFO = 1.9

_SECOES_PRINCIPAIS = {
    "resumo": "resumo",
    "summary": "resumo",
    "sobre": "resumo",
    "about": "resumo",
    "experiencia": "experiencia",
    "experience": "experiencia",
    "formacao academica": "formacao",
    "formacao": "formacao",
    "education": "formacao",
}
_SECOES_LATERAIS = {
    "contato": "contato",
    "contact": "contato",
    "principais competencias": "competencia",
    "top skills": "competencia",
    "competencias": "competencia",
    "languages": "idioma",
    "idiomas": "idioma",
    "certifications": "certificacao",
    "certificacoes": "certificacao",
    "honors-awards": "premio",
    "honors awards": "premio",
    "premios": "premio",
    "publications": "publicacao",
    "publicacoes": "publicacao",
}
_MESES = {
    nome: n
    for n, nomes in enumerate(
        [
            ("janeiro", "january", "jan"),
            ("fevereiro", "february", "fev", "feb"),
            ("marco", "march", "mar"),
            ("abril", "april", "abr", "apr"),
            ("maio", "may", "mai"),
            ("junho", "june", "jun"),
            ("julho", "july", "jul"),
            ("agosto", "august", "ago", "aug"),
            ("setembro", "september", "set", "sep", "sept"),
            ("outubro", "october", "out", "oct"),
            ("novembro", "november", "nov"),
            ("dezembro", "december", "dez", "dec"),
        ],
        start=1,
    )
    for nome in nomes
}
_ATUAL = {"present", "presente", "o momento", "momento", "atual", "hoje", "now"}
_DATA = re.compile(r"(?:([a-z]+)\.?\s+(?:de\s+)?)?(\d{4})")
_PERIODO = re.compile(r"^(?P<inicio>[^()]+?)(?:\s+[-–]\s+(?P<fim>[^()]+?))?\s*(?:\([^)]*\))?\s*$")
_IDIOMAS = {
    "portuguese": "Português",
    "english": "Inglês",
    "spanish": "Espanhol",
    "french": "Francês",
    "german": "Alemão",
    "italian": "Italiano",
    "japanese": "Japonês",
    "chinese": "Chinês",
}
_NIVEIS = {
    "native or bilingual": "nativo ou bilíngue",
    "full professional": "profissional pleno",
    "professional working": "profissional",
    "limited working": "limitado",
    "elementary": "básico",
}
_ROTULO_CONTATO = re.compile(
    r"\s*\((LinkedIn|Portfolio|Other|Company|Personal|Blog|Mobile|Home|Work|"
    r"Outro|Empresa|Pessoal|Celular|Residencial|Trabalho)\)\s*$",
    re.IGNORECASE,
)


class ErroLeitura(ValueError):
    pass


@dataclass
class Linha:
    pagina: int
    top: float
    x0: float
    tamanho: float
    cinza: bool
    texto: str

    @property
    def lateral(self) -> bool:
        return self.x0 < _LATERAL_ATE_X


@dataclass
class Descricao:
    """Texto livre de um cargo (ou o resumo, sem cargo): vai para a IA extrair fatos."""

    empresa: str | None
    cargo: str | None
    periodo: Periodo | None
    texto: str


@dataclass
class PerfilLinkedin:
    nome: str = ""
    titulo: str = ""
    local: str = ""
    candidatos: list[Candidato] = field(default_factory=list)
    descricoes: list[Descricao] = field(default_factory=list)


# --- datas ------------------------------------------------------------------------


def _data(texto: str) -> str | None:
    """'agosto de 2024' → '2024-08'; '2007' → '2007'. ValueError se não for data."""
    m = _DATA.fullmatch(sem_acento(texto).casefold().strip())
    if not m:
        raise ValueError(texto)
    mes, ano = m.groups()
    if mes is None:
        return ano
    if mes not in _MESES:
        raise ValueError(texto)
    return f"{ano}-{_MESES[mes]:02d}"


def ler_periodo(texto: str) -> Periodo | None:
    """'março de 2021 - agosto de 2021 (6 meses)' → Periodo; None se a linha não é período."""
    m = _PERIODO.match(texto.strip())
    if not m:
        return None
    try:
        inicio = _data(m.group("inicio"))
        fim_texto = m.group("fim")
        if fim_texto is None:
            return Periodo(inicio=inicio, fim=inicio)
        fim = None if sem_acento(fim_texto).casefold().strip() in _ATUAL else _data(fim_texto)
    except ValueError:
        return None
    return Periodo(inicio=inicio, fim=fim)


# --- PDF → linhas -------------------------------------------------------------------


def _cinza(cor) -> bool:
    if not cor:
        return False
    valores = [float(v) for v in (cor if isinstance(cor, list | tuple) else [cor])]
    if len(valores) == 4:  # CMYK
        return False
    media = sum(valores) / len(valores)
    return 0.5 < media < 0.8


def linhas_do_pdf(arquivo: bytes | Path) -> list[Linha]:
    import pdfplumber  # lento para importar; só quando há PDF para ler
    from pdfplumber.utils.exceptions import PdfminerException

    dados = arquivo.read_bytes() if isinstance(arquivo, Path) else arquivo
    try:
        pdf = pdfplumber.open(io.BytesIO(dados))
    except PdfminerException as erro:
        raise ErroLeitura("O arquivo não é um PDF que dê para ler.") from erro
    linhas: list[Linha] = []
    with pdf:
        for n, pagina in enumerate(pdf.pages, start=1):
            grupos: dict[tuple, list[dict]] = {}
            for c in pagina.chars:
                chave = (
                    round(c["top"]),
                    c["x0"] < _LATERAL_ATE_X,
                    round(c["size"], 1),
                    _cinza(c.get("non_stroking_color")),
                )
                grupos.setdefault(chave, []).append(c)
            for (top, _, tamanho, cinza), chars in grupos.items():
                chars.sort(key=lambda c: c["x0"])
                texto = "".join(c["text"] for c in chars).strip()
                if texto:
                    x0 = min(c["x0"] for c in chars)
                    linhas.append(Linha(n, top, x0, tamanho, cinza, texto))
    linhas.sort(key=lambda linha: (linha.pagina, linha.top, linha.x0))
    return linhas


# --- linhas → perfil ----------------------------------------------------------------


def _chave_secao(texto: str) -> str:
    return re.sub(r"\s+", " ", sem_acento(texto).casefold()).strip()


def _juntar(anterior: str, proxima: str) -> str:
    if anterior.endswith(("-", "/")) and not anterior.endswith(" -"):
        return anterior + proxima
    return f"{anterior} {proxima}"


def _itens_laterais(linhas: list[Linha]) -> list[tuple[str, list[str]]]:
    """(seção, itens): linhas próximas uma da outra são o mesmo item quebrado."""
    secoes: list[tuple[str, list[str]]] = []
    anterior: Linha | None = None
    for linha in linhas:
        if linha.tamanho >= _TITULO_LATERAL:
            secoes.append((_SECOES_LATERAIS.get(_chave_secao(linha.texto), ""), []))
            anterior = None
            continue
        if not secoes:
            continue
        secao, itens = secoes[-1]
        mesma = anterior is not None and anterior.pagina == linha.pagina
        # No contato o espaçamento não separa itens; o rótulo cinza, "(LinkedIn)", fecha o item.
        fechado = secao == "contato" and bool(itens) and _ROTULO_CONTATO.search(itens[-1])
        if itens and mesma and not fechado and linha.top - anterior.top < _QUEBRA_LATERAL:
            itens[-1] = _juntar(itens[-1], linha.texto)
        else:
            itens.append(linha.texto)
        anterior = linha
    return secoes


def _contato(item: str) -> Candidato | None:
    texto = _ROTULO_CONTATO.sub("", item).strip().rstrip("/")
    texto = re.sub(r"^(https?://)?(www\.)?", "", texto)
    if not texto:
        return None
    if "@" in texto and " " not in texto:
        return Candidato(
            tipo="contato", texto=f"E-mail: {texto}", fonte=FONTE, trecho=item, nao_enviar_ia=True
        )
    if re.fullmatch(r"[+()\d\s-]{8,}", texto):
        return Candidato(
            tipo="contato", texto=f"Telefone: {texto}", fonte=FONTE, trecho=item, nao_enviar_ia=True
        )
    if texto.casefold().startswith("linkedin.com/"):
        texto = f"LinkedIn: {texto}"
    return Candidato(tipo="contato", texto=texto, fonte=FONTE, trecho=item)


def _idioma(item: str) -> Candidato:
    m = re.fullmatch(r"(.+?)\s*\((.+)\)", item)
    nome, nivel = (m.group(1), m.group(2)) if m else (item, "")
    nome = _IDIOMAS.get(nome.casefold(), nome)
    nivel = _NIVEIS.get(nivel.casefold(), nivel.casefold())
    texto = f"{nome}: {nivel}" if nivel else nome
    return Candidato(tipo="idioma", texto=texto, fonte=FONTE, trecho=item)


def _lateral(perfil: PerfilLinkedin, linhas: list[Linha]) -> None:
    for secao, itens in _itens_laterais(linhas):
        for item in itens:
            if secao == "contato":
                candidato = _contato(item)
            elif secao == "idioma":
                candidato = _idioma(item)
            elif secao:
                candidato = Candidato(tipo=secao, texto=item, fonte=FONTE, trecho=item)
            else:
                candidato = None
            if candidato:
                perfil.candidatos.append(candidato)


@dataclass
class _Cargo:
    empresa: str
    cargo: str
    trecho: list[str]
    periodo: Periodo | None = None
    corpo: list[Linha] = field(default_factory=list)


def _abre_paragrafo(anterior: Linha | None, linha: Linha) -> bool:
    if anterior is None or linha.texto.startswith(("•", "- ", "– ")):
        return True
    if anterior.pagina != linha.pagina:  # sem espaço para medir: vale a pontuação
        return anterior.texto.endswith((".", ":", ";", "!", "?"))
    return linha.top - anterior.top > linha.tamanho * _PARAGRAFO


def _paragrafos(linhas: list[Linha]) -> list[str]:
    """Junta linhas quebradas; espaço grande ou marcador ('•', '-') abre parágrafo."""
    paragrafos: list[str] = []
    for i, linha in enumerate(linhas):
        novo = _abre_paragrafo(linhas[i - 1] if i else None, linha)
        if novo:
            paragrafos.append(linha.texto)
        else:
            paragrafos[-1] = _juntar(paragrafos[-1], linha.texto)
    return paragrafos


def _experiencia(perfil: PerfilLinkedin, linhas: list[Linha]) -> None:
    """Empresa (12 pt), cargos (11,5 pt) e, em cada cargo: período, local (cinza) e descrição.

    Linhas de corpo entre a empresa e o primeiro cargo são a duração total; ficam de fora.
    """
    cargos: list[_Cargo] = []
    empresa = ""
    atual: _Cargo | None = None
    anterior: Linha | None = None
    for linha in linhas:
        if linha.tamanho >= _EMPRESA:
            seguida = anterior is not None and anterior.tamanho >= _EMPRESA
            empresa = _juntar(empresa, linha.texto) if seguida else linha.texto
            atual = None
        elif linha.tamanho >= _CARGO:
            if atual and anterior is not None and _CARGO <= anterior.tamanho < _EMPRESA:
                atual.cargo = _juntar(atual.cargo, linha.texto)
                atual.trecho[-1] = atual.cargo
            elif empresa:
                atual = _Cargo(empresa, linha.texto, [empresa, linha.texto])
                cargos.append(atual)
        elif atual:
            periodo = None if atual.periodo or atual.corpo else ler_periodo(linha.texto)
            if periodo:
                atual.periodo = periodo
                atual.trecho.append(linha.texto)
            elif not (linha.cinza and not atual.corpo):  # local do cargo
                atual.corpo.append(linha)
        anterior = linha
    for cargo in cargos:
        perfil.candidatos.append(
            Candidato(
                tipo="cargo",
                texto=f"{cargo.cargo} — {cargo.empresa}",
                empresa=cargo.empresa,
                cargo=cargo.cargo,
                periodo=cargo.periodo,
                fonte=FONTE,
                trecho="\n".join(cargo.trecho),
            )
        )
        if cargo.corpo:
            texto = "\n".join(_paragrafos(cargo.corpo))
            perfil.descricoes.append(Descricao(cargo.empresa, cargo.cargo, cargo.periodo, texto))


def _formacao(perfil: PerfilLinkedin, linhas: list[Linha]) -> None:
    escolas: list[tuple[str, list[str]]] = []
    for linha in linhas:
        if linha.tamanho >= _EMPRESA:
            escolas.append((linha.texto, []))
        elif escolas:
            escolas[-1][1].append(linha.texto)
    for escola, partes in escolas:
        curso = ""
        for parte in partes:
            curso = _juntar(curso, parte) if curso else parte
        periodo = None
        if m := re.search(r"\s*·\s*\(([^()]+)\)\s*$", curso):
            periodo = ler_periodo(m.group(1))
            curso = curso[: m.start()]
        curso = curso.strip()
        texto = f"{curso} — {escola}" if curso else escola
        trecho = "\n".join([escola, *partes])
        perfil.candidatos.append(
            Candidato(
                tipo="formacao",
                texto=texto,
                empresa=escola,
                periodo=periodo,
                fonte=FONTE,
                trecho=trecho,
            )
        )


def interpretar(linhas: list[Linha]) -> PerfilLinkedin:
    # O LinkedIn grava "&amp;" literal no PDF.
    linhas = [replace(x, texto=html.unescape(x.texto)) for x in linhas]
    perfil = PerfilLinkedin()
    principal = [x for x in linhas if not x.lateral and x.tamanho > _RODAPE]
    por_secao: dict[str, list[Linha]] = {}
    secao: str | None = None
    for linha in principal:
        if linha.tamanho >= _NOME and not perfil.nome:
            perfil.nome = linha.texto
        elif linha.tamanho >= _TITULO_SECAO:
            secao = _SECOES_PRINCIPAIS.get(_chave_secao(linha.texto), "outra")
            por_secao.setdefault(secao, [])
        elif secao is None and perfil.nome:
            if linha.cinza:
                perfil.local = linha.texto
            else:
                perfil.titulo = (
                    _juntar(perfil.titulo, linha.texto) if perfil.titulo else linha.texto
                )
        elif secao:
            por_secao.setdefault(secao, []).append(linha)
    if not perfil.nome or "experiencia" not in por_secao:
        raise ErroLeitura(
            "O PDF não parece ser o do LinkedIn (Perfil → Recursos → Salvar como PDF): "
            "não achei o nome nem a seção de experiência."
        )

    _lateral(perfil, [x for x in linhas if x.lateral and x.tamanho > _RODAPE])
    if perfil.local:
        perfil.candidatos.append(
            Candidato(tipo="contato", texto=perfil.local, fonte=FONTE, trecho=perfil.local)
        )
    if resumo := por_secao.get("resumo"):
        perfil.descricoes.append(Descricao(None, None, None, "\n".join(_paragrafos(resumo))))
    _experiencia(perfil, por_secao["experiencia"])
    _formacao(perfil, por_secao.get("formacao", []))
    return perfil


def ler_linkedin_pdf(arquivo: bytes | Path) -> PerfilLinkedin:
    return interpretar(linhas_do_pdf(arquivo))
