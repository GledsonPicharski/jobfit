"""O conteúdo de um CV: o que a IA redige, o que a pessoa edita e o que o PDF mostra."""

from typing import Literal

from pydantic import BaseModel, Field

Idioma = Literal["pt", "en"]


class Frase(BaseModel):
    texto: str = Field(min_length=1, max_length=600)
    fatos: list[str] = Field(default_factory=list, max_length=8)


class ExperienciaRedigida(BaseModel):
    cargo_id: str
    cargo_traduzido: str | None = Field(default=None, max_length=150)
    bullets: list[Frase] = Field(default_factory=list, max_length=8)


class CVRedigido(BaseModel):
    """A saída da IA (`redigir_cv`)."""

    titulo: Frase
    resumo: list[Frase] = Field(default_factory=list, max_length=5)
    experiencias: list[ExperienciaRedigida] = Field(default_factory=list, max_length=20)
    competencias: list[Frase] = Field(default_factory=list, max_length=25)
    formacao: list[Frase] = Field(default_factory=list, max_length=10)
    idiomas: list[Frase] = Field(default_factory=list, max_length=6)
    certificacoes: list[Frase] = Field(default_factory=list, max_length=10)
    # prêmios, publicações, docência e mentoria
    outros: list[Frase] = Field(default_factory=list, max_length=8)


class Experiencia(BaseModel):
    cargo_id: str
    titulo: str  # o cargo como sai no CV: o do dossiê, o `cargo_en` ou a tradução a confirmar
    bullets: list[Frase] = Field(default_factory=list)


class Rascunho(BaseModel):
    """O CV que a pessoa revisa: a estrutura do código com as frases da IA."""

    idioma: Idioma
    titulo: Frase
    resumo: list[Frase] = Field(default_factory=list)
    experiencias: list[Experiencia] = Field(default_factory=list)
    competencias: list[Frase] = Field(default_factory=list)
    formacao: list[Frase] = Field(default_factory=list)
    idiomas: list[Frase] = Field(default_factory=list)
    certificacoes: list[Frase] = Field(default_factory=list)
    outros: list[Frase] = Field(default_factory=list)


SECOES_DE_FRASES = ("resumo", "competencias", "formacao", "idiomas", "certificacoes", "outros")
