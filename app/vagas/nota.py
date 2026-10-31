"""Nota de compatibilidade: a IA julga cada requisito, o código calcula a nota (regra 10).

Soma ponderada dos julgamentos, de 0 a 100. Pesos, valores e faixas vêm de
`config/avaliacao.yaml`, para serem calibrados pelos evals sem mexer no código.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from app.arquivos import ler_texto
from app.validacao import descrever_erro

Peso = Literal["obrigatorio", "desejavel"]
Decisao = Literal["atende", "parcial", "nao_sei", "nao_atende"]

CONFIG_PADRAO = Path(__file__).resolve().parents[2] / "config" / "avaliacao.yaml"


class ErroConfigAvaliacao(ValueError):
    pass


class ConfigAvaliacao(BaseModel):
    model_config = ConfigDict(frozen=True)

    pesos: dict[Peso, float]
    valores: dict[Decisao, float]
    faixas: dict[Literal["A", "B", "C"], int]
    corte: int
    teto_obrigatorio_faltando: int

    @model_validator(mode="after")
    def _coerente(self) -> "ConfigAvaliacao":
        if not self.faixas["A"] > self.faixas["B"] > self.faixas["C"]:
            raise ValueError("as faixas precisam ser decrescentes (A > B > C)")
        if any(not 0 <= v <= 1 for v in self.valores.values()):
            raise ValueError("os valores das decisões vão de 0 a 1")
        return self

    def faixa(self, valor: int) -> str:
        return next((f for f in ("A", "B", "C") if valor >= self.faixas[f]), "D")


def carregar_config(caminho: Path = CONFIG_PADRAO) -> ConfigAvaliacao:
    try:
        return ConfigAvaliacao.model_validate(yaml.safe_load(ler_texto(caminho)))
    except ValidationError as erro:
        detalhes = "; ".join(descrever_erro(e) for e in erro.errors())
        raise ErroConfigAvaliacao(f"{caminho.name} inválido: {detalhes}") from erro


@dataclass(frozen=True)
class Item:
    peso: Peso
    decisao: Decisao
    aplica: bool = True  # "não se aplica" tira o requisito da conta


@dataclass(frozen=True)
class Nota:
    valor: int
    faixa: str
    recomenda: bool
    obrigatorio_faltando: bool


def calcular_nota(itens: list[Item], config: ConfigAvaliacao) -> Nota | None:
    """None quando não sobra requisito para julgar."""
    contam = [i for i in itens if i.aplica]
    total = sum(config.pesos[i.peso] for i in contam)
    if not total:
        return None
    soma = sum(config.pesos[i.peso] * config.valores[i.decisao] for i in contam)
    valor = int((Decimal(str(soma)) * 100 / Decimal(str(total))).quantize(0, ROUND_HALF_UP))
    faltando = any(i.peso == "obrigatorio" and i.decisao == "nao_atende" for i in contam)
    if faltando:
        valor = min(valor, config.teto_obrigatorio_faltando)
    return Nota(valor, config.faixa(valor), valor >= config.corte, faltando)
