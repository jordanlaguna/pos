"""
Los «no» del negocio.

Son excepciones propias y no `HTTPException` a propósito: el dominio no sabe
que existe HTTP. Traducirlas a un código de estado es trabajo de la capa de
interfaz, y es lo que permite probar una regla sin levantar un servidor.

Cada una lleva los datos con los que se puede armar un mensaje. El texto para el
cajero se escribe arriba, en español; acá solo va lo que pasó.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base de todo lo que el negocio rechaza."""


# ------------------------------------------------------------------- valores

class InvalidAmount(DomainError):
    """Un monto que no es un número utilizable."""

    def __init__(self, value: object) -> None:
        super().__init__(f"monto no válido: {value!r}")
        self.value = value


class InvalidQuantity(DomainError):
    """Una cantidad que no tiene sentido: cero, negativa o fraccionaria."""

    def __init__(self, value: object) -> None:
        super().__init__(f"cantidad no válida: {value!r}")
        self.value = value


class InvalidTaxRate(DomainError):
    """Una tasa fuera de 0..1. El 13 % es 0,13, no 13."""

    def __init__(self, value: object) -> None:
        super().__init__(f"tasa de impuesto no válida: {value!r}")
        self.value = value


class InvalidBarcode(DomainError):
    """Un código de barras vacío o con caracteres que un lector no produce."""

    def __init__(self, value: object, motivo: str) -> None:
        super().__init__(f"código de barras no válido ({motivo}): {value!r}")
        self.value = value
        self.motivo = motivo


# ------------------------------------------------------------------- reglas

class InsufficientStock(DomainError):
    """Se pidieron más unidades de las que hay."""

    def __init__(self, product_id: int, available: int, requested: int) -> None:
        super().__init__(
            f"existencias insuficientes del producto {product_id}: "
            f"hay {available} y se piden {requested}"
        )
        self.product_id = product_id
        self.available = available
        self.requested = requested


class InsufficientCash(DomainError):
    """Se quiso sacar de la gaveta más efectivo del que hay."""

    def __init__(self, available: object, requested: object) -> None:
        super().__init__(f"en caja hay {available} y se quieren sacar {requested}")
        self.available = available
        self.requested = requested


class EmptySale(DomainError):
    """Una venta sin líneas no es una venta."""

    def __init__(self) -> None:
        super().__init__("la venta no tiene productos")


class NotSoldInThisSale(DomainError):
    """Se quiso devolver algo que esa venta no llevaba."""

    def __init__(self, product_id: int) -> None:
        super().__init__(f"el producto {product_id} no pertenece a esta venta")
        self.product_id = product_id


class ExcessiveReturn(DomainError):
    """Se quiso devolver más unidades de las que quedan por devolver."""

    def __init__(self, product_id: int, remaining: int, requested: int) -> None:
        super().__init__(
            f"del producto {product_id} quedan {remaining} unidades por devolver "
            f"y se piden {requested}"
        )
        self.product_id = product_id
        self.remaining = remaining
        self.requested = requested


class DuplicateSaleNumber(DomainError):
    """Dos ventas con el mismo número son dos facturas con el mismo
    consecutivo, y eso Hacienda no lo perdona."""

    def __init__(self, sale_number: str) -> None:
        super().__init__(f"ya existe una venta con el número {sale_number}")
        self.sale_number = sale_number


class TotalsMismatch(DomainError):
    """Lo que declaró el POS no es lo que da el servidor al recalcular."""

    def __init__(self, campo: str, declarado: object, calculado: object) -> None:
        super().__init__(
            f"el {campo} declarado ({declarado}) no coincide con el calculado ({calculado})"
        )
        self.campo = campo
        self.declarado = declarado
        self.calculado = calculado


class InsufficientPayment(DomainError):
    """El efectivo recibido no alcanza para el total."""

    def __init__(self, received: object, total: object) -> None:
        super().__init__(f"se recibieron {received} y el total es {total}")
        self.received = received
        self.total = total


class InvalidSource(DomainError):
    """Una entrada de mercadería que no dice de dónde salió."""

    def __init__(self, source: object) -> None:
        super().__init__(f"origen de entrada no válido: {source!r}")
        self.source = source


class DuplicateDocument(DomainError):
    """La misma factura de proveedor, cargada dos veces."""

    def __init__(self, document_number: str) -> None:
        super().__init__(f"el documento {document_number} ya se cargó")
        self.document_number = document_number


class BarcodeTaken(DomainError):
    """Se quiso crear un producto con un código que ya existe."""

    def __init__(self, barcode: str) -> None:
        super().__init__(f"ya hay un producto con el código {barcode}")
        self.barcode = barcode


class LineWithoutProduct(DomainError):
    """Una línea que no dice qué producto entra ni cuál crear."""

    def __init__(self, index: int) -> None:
        super().__init__(f"la línea {index} no indica producto")
        self.index = index


class AlreadyCancelled(DomainError):
    def __init__(self, entry_id: int) -> None:
        super().__init__(f"la entrada {entry_id} ya está anulada")
        self.entry_id = entry_id


class CannotCancel(DomainError):
    """Anular dejaría el inventario en negativo: parte ya se vendió."""

    def __init__(self, product_id: int, available: int, added: int) -> None:
        super().__init__(
            f"del producto {product_id} quedan {available} unidades y la entrada agregó {added}"
        )
        self.product_id = product_id
        self.available = available
        self.added = added


class InvalidMovement(DomainError):
    """Un movimiento de caja mal formado: tipo desconocido, monto o motivo."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo
