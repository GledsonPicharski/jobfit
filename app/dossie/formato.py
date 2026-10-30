"""Leitura e escrita do `dossie.md`: narrativa livre mais blocos ```` ```fatos ```` em YAML.

Ida e volta sem perda: o que não foi alterado sai byte a byte como entrou, inclusive
comentários e a formatação de quem editou à mão. Num bloco alterado, só o fato que mudou
é reserializado; os vizinhos e os comentários entre eles ficam como estavam.
"""

import re
from dataclasses import dataclass, field
from typing import Any

import yaml
from pydantic import ValidationError

from app.dossie.modelos import Fato
from app.validacao import descrever_erro

_ABRE_CERCA = re.compile(r"^(`{3,}|~{3,})\s*([^\s`]*)")
_ORDEM_CAMPOS = (
    "id",
    "tipo",
    "texto",
    "empresa",
    "cargo",
    "periodo",
    "metricas",
    "origem",
    "status",
    "privado",
)


class ErroDossie(ValueError):
    def __init__(self, linha: int, mensagem: str):
        super().__init__(f"Linha {linha}: {mensagem}")
        self.linha = linha
        self.mensagem = mensagem


@dataclass
class Texto:
    conteudo: str


@dataclass
class Trecho:
    """Um fato como foi lido: o texto dele e o que vem depois (linhas em branco, comentários)."""

    fato: Fato
    texto: str
    depois: str


@dataclass
class BlocoFatos:
    abertura: str
    bruto: str
    fechamento: str
    fatos: list[Fato]
    linha: int = 0  # linha do arquivo onde começa o conteúdo do bloco
    alterado: bool = False
    antes: str = ""  # comentários antes do primeiro fato
    trechos: list[Trecho] = field(default_factory=list)

    def conteudo(self) -> str:
        if not self.alterado:
            return self.bruto
        if not self.trechos:
            return serializar_fatos(self.fatos)
        lidos = {t.fato.id: t for t in self.trechos}
        partes = [self.antes]
        for fato in self.fatos:
            lido = lidos.get(fato.id)
            if lido and lido.fato == fato:
                partes.append(lido.texto)
            else:
                partes.append(serializar_fatos([fato]))
            if lido and lido is not self.trechos[-1]:
                partes.append(lido.depois)
        partes.append(self.trechos[-1].depois)  # o fim do bloco, depois do último fato lido
        return "".join(partes)


@dataclass
class Cabecalho:
    abertura: str
    linhas: list[str]
    fechamento: str


@dataclass
class Documento:
    cabecalho: Cabecalho | None
    metadados: dict[str, Any]
    partes: list[Texto | BlocoFatos] = field(default_factory=list)

    @property
    def blocos(self) -> list[BlocoFatos]:
        return [p for p in self.partes if isinstance(p, BlocoFatos)]

    @property
    def fatos(self) -> list[Fato]:
        return [f for bloco in self.blocos for f in bloco.fatos]

    def fato(self, fato_id: str) -> Fato:
        for f in self.fatos:
            if f.id == fato_id:
                return f
        raise KeyError(fato_id)

    def substituir_fato(self, fato: Fato) -> None:
        for bloco in self.blocos:
            for i, atual in enumerate(bloco.fatos):
                if atual.id == fato.id:
                    bloco.fatos[i] = fato
                    bloco.alterado = True
                    return
        raise KeyError(fato.id)

    def definir_metadado(self, chave: str, valor: Any) -> None:
        """Troca só a linha da chave no frontmatter; o resto fica como a pessoa escreveu."""
        linha = f"{chave}: {_escalar(valor)}\n"
        self.metadados[chave] = valor
        if self.cabecalho is None:
            self.cabecalho = Cabecalho("---\n", [linha], "---\n")
            return
        padrao = re.compile(rf"^{re.escape(chave)}\s*:")
        for i, atual in enumerate(self.cabecalho.linhas):
            if padrao.match(atual):
                self.cabecalho.linhas[i] = linha
                return
        self.cabecalho.linhas.append(linha)


# --- leitura ------------------------------------------------------------------


def normalizar(texto: str) -> str:
    # O Bloco de Notas grava BOM e CRLF; o dossiê é sempre UTF-8 com LF.
    return texto.removeprefix("﻿").replace("\r\n", "\n").replace("\r", "\n")


def _linha_do_erro_yaml(erro: yaml.YAMLError, primeira_linha: int) -> int:
    marca = getattr(erro, "problem_mark", None) or getattr(erro, "context_mark", None)
    return primeira_linha + (marca.line if marca else 0)


def _ler_cabecalho(linhas: list[str]) -> tuple[Cabecalho | None, dict[str, Any], int]:
    if not linhas or linhas[0].rstrip() != "---":
        return None, {}, 0
    fim = next((i for i in range(1, len(linhas)) if linhas[i].rstrip() in ("---", "...")), None)
    if fim is None:
        raise ErroDossie(1, "o cabeçalho aberto com --- não foi fechado com outra linha ---.")
    try:
        dados = yaml.safe_load("".join(linhas[1:fim]))
    except yaml.YAMLError as erro:
        raise ErroDossie(
            _linha_do_erro_yaml(erro, 2), f"YAML inválido no cabeçalho: {erro}"
        ) from erro
    if dados is None:
        dados = {}
    if not isinstance(dados, dict):
        raise ErroDossie(2, "o cabeçalho precisa ter linhas no formato chave: valor.")
    return Cabecalho(linhas[0], linhas[1:fim], linhas[fim]), dados, fim + 1


def _fecha_cerca(linha: str, cerca: str) -> bool:
    texto = linha.strip()
    return len(texto) >= len(cerca) and set(texto) == {cerca[0]}


def _ler_fatos(conteudo: str, primeira_linha: int) -> list[tuple[Fato, int]]:
    """Os fatos do bloco, cada um com a linha do arquivo onde começa (`- id:`)."""
    try:
        no = yaml.compose(conteudo, Loader=yaml.SafeLoader)
        dados = yaml.safe_load(conteudo)
    except yaml.YAMLError as erro:
        linha = _linha_do_erro_yaml(erro, primeira_linha)
        raise ErroDossie(linha, f"YAML inválido no bloco de fatos: {erro}") from erro
    if dados is None:
        return []
    if not isinstance(dados, list) or not isinstance(no, yaml.SequenceNode):
        raise ErroDossie(
            primeira_linha, "o bloco de fatos precisa ser uma lista (cada fato começa com '- id:')."
        )
    fatos = []
    for item, no_item in zip(dados, no.value, strict=True):
        linha = primeira_linha + no_item.start_mark.line
        if not isinstance(item, dict):
            raise ErroDossie(linha, "cada fato precisa ter campos no formato chave: valor.")
        try:
            fatos.append((Fato.model_validate(item), linha))
        except ValidationError as erro:
            problemas = "; ".join(descrever_erro(e, raiz="fato") for e in erro.errors())
            raise ErroDossie(linha, f"fato {item.get('id', 'sem id')}: {problemas}") from erro
    return fatos


def _so_comentario(linha: str) -> bool:
    texto = linha.strip()
    return not texto or texto.startswith("#")


def _trechos(conteudo: str, fatos: list[Fato], inicios: list[int]) -> tuple[str, list[Trecho]]:
    """Corta o bloco em um trecho por fato. Sem cortes seguros, devolve vazio (reserializa)."""
    linhas = conteudo.splitlines(keepends=True)
    if not fatos or inicios != sorted(set(inicios)):
        return "", []
    trechos = []
    for n, (fato, inicio) in enumerate(zip(fatos, inicios, strict=True)):
        fim = inicios[n + 1] if n + 1 < len(inicios) else len(linhas)
        corte = fim
        while corte > inicio + 1 and _so_comentario(linhas[corte - 1]):
            corte -= 1
        trechos.append(Trecho(fato, "".join(linhas[inicio:corte]), "".join(linhas[corte:fim])))
    return "".join(linhas[: inicios[0]]), trechos


def ler_dossie(texto: str) -> Documento:
    linhas = normalizar(texto).splitlines(keepends=True)
    cabecalho, metadados, i = _ler_cabecalho(linhas)
    doc = Documento(cabecalho, metadados)
    texto_atual: list[str] = []
    ids: dict[str, int] = {}
    cerca: str | None = None  # dentro de um bloco de código comum

    def fechar_texto() -> None:
        if texto_atual:
            doc.partes.append(Texto("".join(texto_atual)))
            texto_atual.clear()

    while i < len(linhas):
        linha = linhas[i]
        if cerca:
            texto_atual.append(linha)
            if _fecha_cerca(linha, cerca):
                cerca = None
            i += 1
            continue
        abre = _ABRE_CERCA.match(linha)
        if not abre:
            texto_atual.append(linha)
            i += 1
            continue
        if abre.group(2) != "fatos":
            cerca = abre.group(1)
            texto_atual.append(linha)
            i += 1
            continue

        fim = next(
            (j for j in range(i + 1, len(linhas)) if _fecha_cerca(linhas[j], abre.group(1))), None
        )
        if fim is None:
            raise ErroDossie(i + 1, "bloco de fatos sem fechar: falta a linha ``` no fim dele.")
        conteudo = "".join(linhas[i + 1 : fim])
        fatos = _ler_fatos(conteudo, i + 2)
        for fato, linha_fato in fatos:
            if fato.id in ids:
                raise ErroDossie(
                    linha_fato, f"ID {fato.id} duplicado (já usado na linha {ids[fato.id]})."
                )
            ids[fato.id] = linha_fato
        fechar_texto()
        lista = [f for f, _ in fatos]
        antes, trechos = _trechos(conteudo, lista, [n - (i + 2) for _, n in fatos])
        bloco = BlocoFatos(
            linha, conteudo, linhas[fim], lista, linha=i + 2, antes=antes, trechos=trechos
        )
        doc.partes.append(bloco)
        i = fim + 1
    fechar_texto()
    return doc


# --- escrita ------------------------------------------------------------------


class _Dumper(yaml.SafeDumper):
    pass


class _NumaLinha(dict):
    """`periodo` e `metricas` ficam numa linha só; o fato em si, em blocos."""


_Dumper.add_representer(
    _NumaLinha,
    lambda dumper, dados: dumper.represent_mapping(
        "tag:yaml.org,2002:map", dados.items(), flow_style=True
    ),
)


def _escalar(valor: Any) -> str:
    texto = yaml.dump(
        valor, Dumper=_Dumper, allow_unicode=True, default_flow_style=True, width=10_000
    )
    return texto.removesuffix("\n...\n").strip()


def _para_yaml(fato: Fato) -> dict[str, Any]:
    dados = fato.model_dump(exclude_none=True)
    saida: dict[str, Any] = {}
    for campo in _ORDEM_CAMPOS:
        valor = dados.pop(campo, None)
        if campo == "periodo" and fato.periodo is not None:
            valor = {"inicio": fato.periodo.inicio, "fim": fato.periodo.fim}
        if isinstance(valor, dict):
            valor = _NumaLinha(valor) if valor else None
        if valor is not None:
            saida[campo] = valor
    if dados.pop("nao_enviar_ia", False):
        saida["nao_enviar_ia"] = True
    saida.update(dados)  # campos escritos à mão, no fim
    return saida


def serializar_fatos(fatos: list[Fato]) -> str:
    if not fatos:
        return ""
    return yaml.dump(
        [_para_yaml(f) for f in fatos],
        Dumper=_Dumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=10_000,
    )


def escrever_dossie(doc: Documento) -> str:
    partes: list[str] = []
    if doc.cabecalho is not None:
        partes += [doc.cabecalho.abertura, *doc.cabecalho.linhas, doc.cabecalho.fechamento]
    for parte in doc.partes:
        if isinstance(parte, Texto):
            partes.append(parte.conteudo)
        else:
            partes += [parte.abertura, parte.conteudo(), parte.fechamento]
    return "".join(partes)
