"""
La tasa de impuesto.

Se guarda entre 0 y 1: el 13 % es `0.13`. El error de escribir `13` es tan fácil
de cometer —y tan caro, porque multiplica la factura por catorce— que el tipo se
niega a construirse con él.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .errors import InvalidTaxRate
from .money import Money

#: Seis decimales alcanzan para cualquier tasa real y evitan que una división
#: entre montos arrastre veinte dígitos.
PRECISION = Decimal("0.000001")


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        candidato = value
    elif isinstance(value, bool):
        raise InvalidTaxRate(value)
    elif isinstance(value, (int, float)):
        candidato = Decimal(str(value))
    elif isinstance(value, str):
        try:
            candidato = Decimal(value.strip())
        except InvalidOperation:
            raise InvalidTaxRate(value) from None
    else:
        raise InvalidTaxRate(value)

    if not candidato.is_finite():
        raise InvalidTaxRate(value)
    return candidato


@dataclass(frozen=True, order=True)
class TaxRate:
    value: Decimal

    def __post_init__(self) -> None:
        crudo = _to_decimal(self.value)
        if crudo < 0 or crudo > 1:
            raise InvalidTaxRate(self.value)
        object.__setattr__(self, "value", crudo.quantize(PRECISION))

    # ------------------------------------------------------------ construir

    @classmethod
    def percent(cls, percentage: object) -> TaxRate:
        """`TaxRate.percent(13)` → 0,13. Para leer lo que escribe una persona."""
        return cls(_to_decimal(percentage) / Decimal(100))

    @classmethod
    def zero(cls) -> TaxRate:
        return cls(Decimal(0))

    @classmethod
    def of_sale(cls, subtotal: Money, tax: Money, default: TaxRate) -> TaxRate:
        """
        La tasa con la que se cobró una venta, reconstruida de sus montos.

        Es la regla de las devoluciones: se reembolsa con la tasa de SU venta y
        no con la configurada hoy. Si el dueño sube el IVA del 13 al 15, lo que
        se devuelve sigue siendo lo que se cobró.

        Con subtotal en cero no hay nada que dividir —una venta regalada, o una
        fila a medias— y se usa la tasa de referencia que pase quien llama.
        """
        if not subtotal.is_positive:
            return default
        return cls((tax.amount / subtotal.amount).quantize(PRECISION))

    # ------------------------------------------------------------ usar

    def apply(self, base: Money) -> Money:
        """El impuesto que le toca a un monto."""
        return base * self.value

    def add_to(self, base: Money) -> Money:
        """El monto con el impuesto encima."""
        return base + self.apply(base)

    @property
    def as_percent(self) -> Decimal:
        return (self.value * 100).normalize()

    def __str__(self) -> str:
        return f"{self.as_percent} %"
