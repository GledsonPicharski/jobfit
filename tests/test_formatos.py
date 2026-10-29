from decimal import Decimal

import pytest

from app.web.formatos import formatar_usd, ler_decimal


@pytest.mark.parametrize(
    ("micro", "texto"),
    [
        (None, "custo desconhecido"),
        (0, "US$ 0,00"),
        (1250, "US$ 0,00125"),
        (1, "US$ 0,000001"),
        (10_000, "US$ 0,01"),
        (2_345_678, "US$ 2,35"),
    ],
)
def test_formatar_usd(micro, texto):
    assert formatar_usd(micro) == texto


@pytest.mark.parametrize(("texto", "valor"), [("2,50", "2.50"), (" 3.1 ", "3.1"), ("0", "0")])
def test_ler_decimal(texto, valor):
    assert ler_decimal(texto) == Decimal(valor)


def test_ler_decimal_invalido():
    with pytest.raises(ValueError, match="inválido"):
        ler_decimal("dois reais")
