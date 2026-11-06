from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.vagas.metadados import Modalidade, Senioridade

Provedor = Literal["manual", "anthropic", "openrouter"]
Nivel = Literal["barato", "forte"]

PROVEDORES: dict[Provedor, str] = {
    "manual": "Manual (copiar e colar no seu chat)",
    "anthropic": "Anthropic (API)",
    "openrouter": "OpenRouter (API)",
}
PROVEDORES_COM_CHAVE: frozenset[Provedor] = frozenset({"anthropic", "openrouter"})

MODELOS_PADRAO: dict[Provedor, dict[Nivel, str]] = {
    "manual": {"barato": "chat", "forte": "chat"},
    "anthropic": {"barato": "claude-haiku-5-5", "forte": "claude-sonnet-5-5"},
    "openrouter": {"barato": "anthropic/claude-haiku-5.5", "forte": "anthropic/claude-sonnet-5.5"},
}


class ConfigIA(BaseModel):
    """Escolhas de IA do perfil. A chave fica no keyring, nunca aqui.

    O padrão é o modo manual: sem chave e sem custo (decisão 0003).
    """

    provedor: Provedor = "manual"
    modelos: dict[Nivel, str] = Field(default_factory=lambda: dict(MODELOS_PADRAO["manual"]))
    teto_diario_usd: Decimal = Field(default=Decimal("2.00"), ge=0)

    def com_provedor(self, provedor: Provedor) -> "ConfigIA":
        """Troca o provedor; modelos que estavam no padrão do antigo passam ao padrão do novo."""
        antigos = MODELOS_PADRAO[self.provedor]
        novos = MODELOS_PADRAO[provedor]
        modelos = {
            nivel: novos[nivel] if nome == antigos[nivel] else nome
            for nivel, nome in self.modelos.items()
        }
        return self.model_copy(update={"provedor": provedor, "modelos": modelos})

    @property
    def precisa_chave(self) -> bool:
        return self.provedor in PROVEDORES_COM_CHAVE


class Criterios(BaseModel):
    """Filtros duros de vaga, aplicados em código antes de qualquer IA (decisão 0006).

    Lista vazia quer dizer "qualquer um". O salário mínimo é privado: nunca vai para a IA.
    """

    modalidades: list[Modalidade] = Field(
        default_factory=lambda: ["remoto", "hibrido", "presencial"]
    )
    cidades: list[str] = Field(default_factory=list)  # para híbrido e presencial
    senioridades: list[Senioridade] = Field(default_factory=list)
    salario_minimo: Decimal | None = Field(default=None, ge=0)  # R$ por mês
    empresas_evitar: list[str] = Field(default_factory=list)
    palavras_evitar: list[str] = Field(default_factory=list)


class Perfil(BaseModel):
    slug: str
    nome: str
    criado_em: datetime
    ia: ConfigIA = Field(default_factory=ConfigIA)
    criterios: Criterios = Field(default_factory=Criterios)
