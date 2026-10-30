"""Um fato do dossiê: a menor unidade que CV, avaliação e LinkedIn podem citar."""

import re
import unicodedata
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TipoFato = Literal[
    "cargo",
    "resultado",
    "competencia",
    "ferramenta",
    "formacao",
    "certificacao",
    "idioma",
    "preferencia",
    "restricao",
    "resposta_padrao",
]
StatusFato = Literal["confirmado", "proposto", "rejeitado"]

_DATA_ISO = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
_ATUAL = {"atual", "o momento", "present", "presente", "hoje"}


def sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def normalizar_tipo(valor: Any) -> Any:
    """Quem edita à mão escreve "Competência" ou "formação"; o código usa sem acento."""
    if isinstance(valor, str):
        return sem_acento(valor).strip().lower().replace(" ", "_")
    return valor


class Periodo(BaseModel):
    """Datas ISO parciais (`2023`, `2023-03`, `2023-03-15`); `fim` vazio quer dizer atual."""

    model_config = ConfigDict(frozen=True)

    inicio: str | None = None
    fim: str | None = None

    @field_validator("inicio", "fim", mode="before")
    @classmethod
    def _data(cls, valor: Any) -> str | None:
        if valor is None:
            return None
        if isinstance(valor, date):  # o YAML lê 2023-03-15 como data
            return valor.isoformat()
        texto = str(valor).strip()
        if not texto or texto.casefold() in _ATUAL:
            return None
        if not _DATA_ISO.fullmatch(texto):
            raise ValueError(f"data {texto!r} fora do formato AAAA, AAAA-MM ou AAAA-MM-DD")
        return texto


class Fato(BaseModel):
    # Campos que a pessoa escreveu à mão e o app não conhece são preservados.
    model_config = ConfigDict(extra="allow")

    id: str = Field(pattern=r"^F-\d{3,}$")
    tipo: TipoFato
    texto: str = Field(min_length=1)
    empresa: str | None = None
    cargo: str | None = None
    periodo: Periodo | None = None
    metricas: dict[str, str | int | float] = Field(default_factory=dict)
    origem: str | None = None
    status: StatusFato = "confirmado"
    privado: bool = False
    nao_enviar_ia: bool = False

    _tipo = field_validator("tipo", mode="before")(normalizar_tipo)

    @field_validator("texto")
    @classmethod
    def _texto(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("o texto do fato está vazio")
        return valor
