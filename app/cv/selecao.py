"""Seleção de fatos para um CV (código, sem IA): o que entra e em que ordem.

Só entram fatos publicáveis (confirmados e sem 🔒, regra 5). Todos os cargos entram; os
recentes levam os resultados da empresa mais relevantes para a vaga, e os antigos só a
linha do cargo. Contato vai para o cabeçalho, renderizado localmente: nunca vai para a IA.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.arquivos import ler_texto
from app.dossie.filtros import fatos_publicaveis
from app.dossie.modelos import Fato
from app.textos import palavras
from app.validacao import descrever_erro

CONFIG_PADRAO = Path(__file__).resolve().parents[2] / "config" / "cv.yaml"

# O que não é conteúdo de CV: fica no dossiê para a avaliação de vagas e para a pessoa.
_FORA_DO_CV = {"preferencia", "restricao", "lacuna", "resposta_padrao"}
_PALAVRAS_VAZIAS = {
    "para", "como", "com", "uma", "que", "dos", "das", "pela", "pelo", "mais", "sobre",
    "with", "and", "the", "for", "from", "into", "your", "our", "you", "will",
}  # fmt: skip


class ErroConfigCV(ValueError):
    pass


class ConfigCV(BaseModel):
    model_config = ConfigDict(frozen=True)

    anos_detalhados: int = Field(ge=1)
    bullets_por_cargo: int = Field(ge=1)
    competencias: int = Field(ge=1)
    certificacoes: int = Field(ge=0)
    premios_publicacoes: int = Field(ge=0)
    docencia_mentoria: int = Field(ge=0)
    frases_resumo: int = Field(ge=1)
    caracteres_por_frase: int = Field(ge=40)


def carregar_config(caminho: Path = CONFIG_PADRAO) -> ConfigCV:
    try:
        return ConfigCV.model_validate(yaml.safe_load(ler_texto(caminho)))
    except ValidationError as erro:
        detalhes = "; ".join(descrever_erro(e) for e in erro.errors())
        raise ErroConfigCV(f"{caminho.name} inválido: {detalhes}") from erro


@dataclass
class CargoSelecionado:
    cargo: Fato
    fatos: list[Fato] = field(default_factory=list)  # candidatos a bullet, por relevância
    detalhado: bool = True


@dataclass
class Selecao:
    cargos: list[CargoSelecionado] = field(default_factory=list)
    soltos: list[Fato] = field(default_factory=list)  # resultados sem cargo: candidatos ao resumo
    competencias: list[Fato] = field(default_factory=list)
    formacao: list[Fato] = field(default_factory=list)
    idiomas: list[Fato] = field(default_factory=list)
    certificacoes: list[Fato] = field(default_factory=list)
    premios: list[Fato] = field(default_factory=list)
    docencia: list[Fato] = field(default_factory=list)
    contato: list[Fato] = field(default_factory=list)

    @property
    def para_ia(self) -> list[Fato]:
        """O que a IA pode ler para redigir: tudo menos o contato."""
        fatos = [c.cargo for c in self.cargos] + [f for c in self.cargos for f in c.fatos]
        for grupo in (
            self.soltos,
            self.competencias,
            self.formacao,
            self.idiomas,
            self.certificacoes,
            self.premios,
            self.docencia,
        ):
            fatos += grupo
        return fatos

    @property
    def todos(self) -> list[Fato]:
        return self.para_ia + self.contato


def _termos(texto: str) -> set[str]:
    return {p for p in palavras(texto).split() if len(p) >= 4 and p not in _PALAVRAS_VAZIAS}


def _texto_completo(fato: Fato) -> str:
    extra = fato.model_extra or {}
    return " ".join(str(v) for v in (fato.texto, extra.get("texto_en"), fato.cargo) if v)


def _ordenar(fatos: list[Fato], termos_vaga: set[str], citados: set[str]) -> list[Fato]:
    def chave(item: tuple[int, Fato]) -> tuple[int, int, int]:
        posicao, fato = item
        em_comum = len(_termos(_texto_completo(fato)) & termos_vaga)
        return (-(fato.id in citados), -em_comum, posicao)

    return [f for _, f in sorted(enumerate(fatos), key=chave)]


def _inicio(fato: Fato) -> str:
    return (fato.periodo.inicio if fato.periodo else None) or ""


def _detalhado(cargo: Fato, config: ConfigCV, hoje: date) -> bool:
    if cargo.periodo is None or cargo.periodo.fim is None:
        return True
    return int(cargo.periodo.fim[:4]) >= hoje.year - config.anos_detalhados


def _mesma_empresa(a: str | None, b: str | None) -> bool:
    return bool(a and b) and palavras(a) == palavras(b)


def selecionar(
    fatos: list[Fato], vaga: str | None, citados: set[str], config: ConfigCV, hoje: date
) -> Selecao:
    """`citados`: fatos que a avaliação da vaga usou em "atende" ou "parcial"."""
    publicaveis = [f for f in fatos_publicaveis(fatos) if f.tipo not in _FORA_DO_CV]
    termos = _termos(vaga or "")

    def ordenados(tipos: set[str], limite: int | None = None) -> list[Fato]:
        grupo = _ordenar([f for f in publicaveis if f.tipo in tipos], termos, citados)
        return grupo[:limite] if limite is not None else grupo

    s = Selecao()
    cargos = sorted((f for f in publicaveis if f.tipo == "cargo"), key=_inicio, reverse=True)
    resultados = [f for f in publicaveis if f.tipo == "resultado"]
    for cargo in cargos:
        detalhado = _detalhado(cargo, config, hoje)
        da_empresa = [f for f in resultados if _mesma_empresa(f.empresa, cargo.empresa)]
        escolhidos = _ordenar(da_empresa, termos, citados)[: config.bullets_por_cargo]
        s.cargos.append(CargoSelecionado(cargo, escolhidos if detalhado else [], detalhado))
    com_cargo = {c.cargo.empresa and palavras(c.cargo.empresa) for c in s.cargos}
    soltos = [f for f in resultados if not f.empresa or palavras(f.empresa) not in com_cargo]
    s.soltos = _ordenar(soltos, termos, citados)[: config.frases_resumo]

    s.competencias = ordenados({"competencia", "ferramenta"}, config.competencias)
    s.formacao = sorted(ordenados({"formacao"}), key=_inicio, reverse=True)
    s.idiomas = ordenados({"idioma"})
    s.certificacoes = ordenados({"certificacao"}, config.certificacoes)
    s.premios = ordenados({"premio", "publicacao"}, config.premios_publicacoes)
    s.docencia = ordenados({"docencia", "mentoria"}, config.docencia_mentoria)
    s.contato = [f for f in publicaveis if f.tipo == "contato"]
    return s


def periodo_legivel(fato: Fato, idioma: str) -> str:
    """ "mar 2023 – atual" ou "Mar 2023 – Present"; só o ano quando o mês não está no dossiê."""
    if fato.periodo is None:
        return ""
    meses = (
        "jan fev mar abr mai jun jul ago set out nov dez"
        if idioma == "pt"
        else "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec"
    ).split()

    def data(valor: str | None) -> str:
        if valor is None:
            return "atual" if idioma == "pt" else "Present"
        if m := re.match(r"^(\d{4})-(\d{2})", valor):
            return f"{meses[int(m.group(2)) - 1]} {m.group(1)}"
        return valor[:4]

    return f"{data(fato.periodo.inicio)} – {data(fato.periodo.fim)}"
