"""
Plata.

Un `float` no sirve para dinero: `0.1 + 0.2` no da `0.3` y un carrito largo
acumula centavos fantasma. Todo lo monetario del dominio pasa por acá, sobre
`Decimal`, que es exacto en base 10.

**Sobre el redondeo.** Se redondea a dos decimales en cada paso, igual que hacía
el WinForms original al escribir `.ToString("0.00")` en la grilla.

El modo es `ROUND_HALF_UP`: el empate se resuelve **alejándose del cero**, así
que `2.665` da `2.67` y `-2.665` da `-2.67`. Es el redondeo comercial de toda la
vida y el que hacía el sistema original.

Hasta el 2026-08-16 este backend usaba `ROUND_HALF_EVEN` —el redondeo bancario—,
no por decisión sino porque es el modo por omisión de Python y nadie lo escribió.
Eso lo dejaba en desacuerdo con el POS, que siempre redondeó medio hacia arriba:
la misma venta daba `2.66` en el servidor y `2.67` en la pantalla. Con precios en
colones enteros no se notaba; con céntimos, sí, y ahora que el servidor
**verifica** los totales que manda el POS (T-108b) un céntimo de diferencia
rechazaría la venta. Los dos lados tienen que redondear igual o no pueden
compararse.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .errors import InvalidAmount

CENTS = Decimal("0.01")

#: El mismo modo tiene que estar en `frontend/src/lib/money.ts`. Si uno cambia y
#: el otro no, el servidor empieza a rechazar ventas por un céntimo.
ROUNDING = ROUND_HALF_UP


def _to_decimal(value: object) -> Decimal:
    """Cualquier cosa razonable → Decimal, o `InvalidAmount`."""
    if isinstance(value, Money):
        return value.amount
    if isinstance(value, Decimal):
        candidato = value
    elif isinstance(value, bool):
        # Antes que `int`: en Python `True` es 1, y un booleano donde va un monto
        # es siempre un error de quien llama, no un uno.
        raise InvalidAmount(value)
    elif isinstance(value, int):
        candidato = Decimal(value)
    elif isinstance(value, float):
        # Por `str` y no directo: `Decimal(0.1)` da la expansión binaria entera,
        # con cincuenta dígitos que nadie escribió.
        candidato = Decimal(str(value))
    elif isinstance(value, str):
        try:
            candidato = Decimal(value.strip())
        except InvalidOperation:
            raise InvalidAmount(value) from None
    else:
        raise InvalidAmount(value)

    if not candidato.is_finite():
        raise InvalidAmount(value)
    return candidato


@dataclass(frozen=True, order=True)
class Money:
    """Un monto, ya redondeado a dos decimales.

    Se normaliza al construirlo, así que `Money(1450) == Money("1450.000")` y no
    hay forma de tener dos montos que valen lo mismo y no son iguales.
    """

    amount: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "amount", _to_decimal(self.amount).quantize(CENTS, rounding=ROUNDING)
        )

    # ------------------------------------------------------------ construir

    @classmethod
    def zero(cls) -> Money:
        return cls(Decimal(0))

    @classmethod
    def sum(cls, montos) -> Money:
        """Suma de una lista, redondeando en cada paso como el original."""
        total = cls.zero()
        for m in montos:
            total = total + m
        return total

    # ------------------------------------------------------------ aritmética

    def __add__(self, other: object) -> Money:
        return Money(self.amount + _to_decimal(other))

    def __sub__(self, other: object) -> Money:
        return Money(self.amount - _to_decimal(other))

    def __mul__(self, factor: object) -> Money:
        """Por una cantidad o una tasa. No existe multiplicar plata por plata."""
        if isinstance(factor, Money):
            raise InvalidAmount(factor)
        return Money(self.amount * _to_decimal(factor))

    __rmul__ = __mul__

    def __neg__(self) -> Money:
        return Money(-self.amount)

    def __abs__(self) -> Money:
        return Money(abs(self.amount))

    # ------------------------------------------------------------ preguntas

    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    @property
    def is_positive(self) -> bool:
        return self.amount > 0

    # ------------------------------------------------------------ salida

    def as_float(self) -> float:
        """Para la frontera: JSON no tiene Decimal.

        Solo en el borde. Adentro, nunca: volver a `float` es reabrir la puerta
        que este módulo existe para cerrar.
        """
        return float(self.amount)

    def __str__(self) -> str:
        return f"{self.amount:.2f}"
