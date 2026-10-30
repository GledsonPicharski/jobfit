"""Esqueleto do dossiê novo e a regra, em código, de onde cada fato aprovado entra."""

import re
from dataclasses import dataclass, field
from datetime import date

from app.dossie.formato import BlocoFatos, Documento, Texto
from app.dossie.modelos import Fato, TipoFato, sem_acento

# Seção de cada tipo: (chave, título usado quando a seção ainda não existe).
_SECOES: dict[str, str] = {
    "objetivo": "Objetivo e preferências",
    "experiencias": "Experiências",
    "formacao": "Formação",
    "competencias": "Competências e ferramentas",
    "idiomas": "Idiomas",
    "certificacoes": "Certificações",
    "respostas": "Respostas de formulário",
}
_SECAO_DO_TIPO: dict[TipoFato, str] = {
    "preferencia": "objetivo",
    "restricao": "objetivo",
    "cargo": "experiencias",
    "resultado": "experiencias",
    "formacao": "formacao",
    "competencia": "competencias",
    "ferramenta": "competencias",
    "idioma": "idiomas",
    "certificacao": "certificacoes",
    "resposta_padrao": "respostas",
}
# Palavras que identificam a seção no título, para aceitar títulos escritos à mão.
_PALAVRAS: dict[str, tuple[str, ...]] = {
    "objetivo": ("objetivo", "preferencia"),
    "experiencias": ("experiencia",),
    "formacao": ("formacao",),
    "competencias": ("competencia", "ferramenta"),
    "idiomas": ("idioma",),
    "certificacoes": ("certifica",),
    "respostas": ("resposta",),
}
_TITULO = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_CERCA = re.compile(r"^(`{3,}|~{3,})")
_ID = re.compile(r"^F-(\d+)$")


def esqueleto(slug: str, nome: str) -> str:
    return f"""---
perfil: {slug}
versao: 1
atualizado: {date.today().isoformat()}
idiomas_cv: [pt]
---
# Dossiê de carreira — {nome}

## 0. Como a IA deve usar este arquivo

Hierarquia de fontes: dossiê confirmado > LinkedIn > CV antigo. Não inventar.
Itens com `privado: true` (🔒) nunca vão para CV, LinkedIn ou e-mail.

## 1. Objetivo e preferências

## 2. Resumo

## 3. Experiências

## 4. Formação

## 5. Competências e ferramentas

## 6. Idiomas

## 7. Certificações
"""


def proximo_id(doc: Documento) -> str:
    numeros = [int(m.group(1)) for f in doc.fatos if (m := _ID.match(f.id))]
    return f"F-{max(numeros, default=0) + 1:03d}"


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", sem_acento(texto).casefold()).strip()


def _explodir(doc: Documento) -> None:
    """Uma parte `Texto` por linha: inserir no meio fica fácil e a escrita não muda."""
    partes: list[Texto | BlocoFatos] = []
    for parte in doc.partes:
        if isinstance(parte, Texto):
            partes += [Texto(linha) for linha in parte.conteudo.splitlines(keepends=True)]
        else:
            partes.append(parte)
    doc.partes = partes


def _titulos(doc: Documento) -> list[tuple[int, int, str]]:
    """(posição na lista de partes, nível, texto normalizado), fora de blocos de código."""
    titulos = []
    cerca: str | None = None
    for i, parte in enumerate(doc.partes):
        if not isinstance(parte, Texto):
            continue
        linha = parte.conteudo
        if abre := _CERCA.match(linha):
            if cerca is None:
                cerca = abre.group(1)
            elif linha.strip() and set(linha.strip()) == {cerca[0]}:
                cerca = None
            continue
        if cerca is None and (m := _TITULO.match(linha)):
            titulos.append((i, len(m.group(1)), _normalizar(m.group(2))))
    return titulos


def _fim(doc: Documento, inicio: int, nivel: int) -> int:
    """Onde termina a seção que começa em `inicio`: no próximo título de nível igual ou acima."""
    for i, n, _ in _titulos(doc):
        if i > inicio and n <= nivel:
            return i
    return len(doc.partes)


def _sem_linhas_em_branco_no_fim(doc: Documento, inicio: int, fim: int) -> int:
    while fim > inicio + 1:
        anterior = doc.partes[fim - 1]
        if not (isinstance(anterior, Texto) and not anterior.conteudo.strip()):
            break
        fim -= 1
    return fim


def _garantir_fim_de_linha(doc: Documento) -> None:
    if doc.partes:
        ultima = doc.partes[-1]
        if isinstance(ultima, Texto) and not ultima.conteudo.endswith("\n"):
            ultima.conteudo += "\n"
        elif isinstance(ultima, BlocoFatos) and not ultima.fechamento.endswith("\n"):
            ultima.fechamento += "\n"


def _secao(doc: Documento, chave: str) -> tuple[int, int]:
    for i, nivel, texto in _titulos(doc):
        if nivel == 2 and any(p in texto for p in _PALAVRAS[chave]):
            return i, _fim(doc, i, 2)
    _garantir_fim_de_linha(doc)
    doc.partes += [Texto("\n"), Texto(f"## {_SECOES[chave]}\n")]
    return len(doc.partes) - 1, len(doc.partes)


def _subsecao_da_empresa(doc: Documento, empresa: str) -> tuple[int, int]:
    inicio, fim = _secao(doc, "experiencias")
    alvo = _normalizar(empresa)
    for i, nivel, texto in _titulos(doc):
        if inicio < i < fim and nivel == 3 and texto.startswith(alvo):
            return i, _fim(doc, i, 3)
    pos = _sem_linhas_em_branco_no_fim(doc, inicio, fim)
    doc.partes[pos:pos] = [Texto("\n"), Texto(f"### {empresa}\n")]
    return pos + 1, pos + 2


def _inserir(doc: Documento, fato: Fato) -> None:
    chave = _SECAO_DO_TIPO[fato.tipo]
    if chave == "experiencias" and fato.empresa:
        inicio, fim = _subsecao_da_empresa(doc, fato.empresa)
    else:
        inicio, fim = _secao(doc, chave)
    blocos = [p for p in doc.partes[inicio:fim] if isinstance(p, BlocoFatos)]
    if blocos:
        blocos[-1].fatos.append(fato)
        blocos[-1].alterado = True
        return
    pos = _sem_linhas_em_branco_no_fim(doc, inicio, fim)
    bloco = BlocoFatos("```fatos\n", "", "```\n", [fato], alterado=True)
    doc.partes[pos:pos] = [Texto("\n"), bloco]


def inserir_fatos(doc: Documento, fatos: list[Fato]) -> None:
    """Com empresa: `### <empresa>` em Experiências. Sem empresa: a seção do tipo."""
    _explodir(doc)
    for fato in fatos:
        _inserir(doc, fato)


@dataclass
class SecaoTela:
    nivel: int
    titulo: str
    fatos: list[Fato] = field(default_factory=list)


def secoes_para_tela(doc: Documento) -> list[SecaoTela]:
    """Títulos e os fatos sob cada um, na ordem do arquivo (sem a narrativa)."""
    secoes: list[SecaoTela] = []
    cerca: str | None = None
    for parte in doc.partes:
        if isinstance(parte, BlocoFatos):
            if not secoes:
                secoes.append(SecaoTela(2, ""))
            secoes[-1].fatos += parte.fatos
            continue
        for linha in parte.conteudo.splitlines():
            if abre := _CERCA.match(linha):
                if cerca is None:
                    cerca = abre.group(1)
                elif set(linha.strip()) == {cerca[0]}:
                    cerca = None
            elif cerca is None and (m := _TITULO.match(linha)) and len(m.group(1)) > 1:
                secoes.append(SecaoTela(len(m.group(1)), m.group(2)))
    return secoes
