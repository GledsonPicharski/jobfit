"""Formatação para as telas, no padrão brasileiro."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.ia.custos import de_micro_usd

UM_CENTAVO = Decimal("0.01")


def formatar_usd(micro: int | None) -> str:
    """Valores abaixo de um centavo mostram as casas necessárias (US$ 0,00125)."""
    if micro is None:
        return "custo desconhecido"
    valor = de_micro_usd(micro)
    texto = f"{valor:.2f}" if valor >= UM_CENTAVO or valor == 0 else f"{valor:.6f}".rstrip("0")
    return "US$ " + texto.replace(".", ",")


def formatar_hora_local(momento: datetime) -> str:
    return momento.astimezone().strftime("%d/%m %H:%M")


def ler_decimal(texto: str) -> Decimal:
    """Aceita "2,50" e "2.50"."""
    try:
        return Decimal(texto.strip().replace(",", "."))
    except InvalidOperation as erro:
        raise ValueError(f"Valor inválido: {texto!r}.") from erro
