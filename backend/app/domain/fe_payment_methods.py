"""
El medio de pago en el código de Hacienda (nota 6 del anexo v4.4, T-716, RN-77).

VentaSys guarda el medio de pago con su nombre —`"Efectivo"`, `"Tarjeta de
crédito"`— porque es lo que se ve en la pantalla y lo que el libro necesita para
asentar. Hacienda lo quiere en dos dígitos. **La traducción vive acá y en un
solo sitio**, con una prueba que la obliga a estar completa: agregar un medio de
pago al POS sin decidir su código rompe la construcción, que es justo cuando hay
que decidirlo y no el día de emitir.

No todos los códigos tienen nombre del lado del POS, y está bien: el cheque, el
recaudado por terceros y la plataforma digital existen en el catálogo y todavía
no son formas de cobrar en VentaSys.
"""

from __future__ import annotations

from typing import Final

from .errors import InvalidSalePaymentMethod
from .sale import PAYMENT_METHODS

#: Los ocho de la nota 6.
CODES: Final = ("01", "02", "03", "04", "05", "06", "07", "99")

CASH: Final = "01"
CARD: Final = "02"
CHECK: Final = "03"
TRANSFER: Final = "04"
THIRD_PARTY: Final = "05"
SINPE: Final = "06"
DIGITAL_PLATFORM: Final = "07"
OTHER: Final = "99"

#: De lo que guarda una venta al código del comprobante.
#:
#: El pago móvil es SINPE MÓVIL (`06`) y no «otros»: en Costa Rica es el mismo
#: servicio, y mandarlo como `99` obligaría a describirlo en la representación
#: gráfica sin ninguna ganancia.
FROM_SALE_METHOD: Final[dict[str, str]] = {
    "Efectivo": CASH,
    "Tarjeta de crédito": CARD,
    "Transferencia bancaria": TRANSFER,
    "Pago móvil": SINPE,
}


def code_for(method: object) -> str:
    """El código de Hacienda de un medio de pago de la venta.

    Se niega con el mismo «no» que `check_payment_method`: un medio que el POS
    no conoce no tiene código, y adivinarle uno sería emitir un comprobante que
    dice que se cobró de una forma que nadie eligió.
    """
    codigo = FROM_SALE_METHOD.get(method)  # type: ignore[arg-type]
    if codigo is None:
        raise InvalidSalePaymentMethod(method)
    return codigo


def check_code(value: object) -> str:
    if value not in CODES:
        raise InvalidSalePaymentMethod(value)
    return str(value)


#: Los medios de pago del POS que todavía no tienen código. Vacío a propósito:
#: lo comprueba `tests/domain/test_fe_payment_methods.py`.
SIN_CODIGO: Final = tuple(m for m in PAYMENT_METHODS if m not in FROM_SALE_METHOD)


__all__ = [
    "CARD",
    "CASH",
    "CHECK",
    "CODES",
    "DIGITAL_PLATFORM",
    "FROM_SALE_METHOD",
    "OTHER",
    "SINPE",
    "SIN_CODIGO",
    "THIRD_PARTY",
    "TRANSFER",
    "check_code",
    "code_for",
]
