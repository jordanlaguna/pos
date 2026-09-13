"""Compras y abonos a proveedor (F10).

La compra en sí viaja por `schemas_stock_entry.py`: es la entrada de mercadería
con tres datos más (plan §12.1). Acá va lo que no cabe en ella.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class SupplierPaymentIn(BaseModel):
    amount: float
    #: 'cash' | 'transfer' | 'other'. Lo valida el dominio, no Pydantic: el
    #: método decide si hay que sacar plata de la gaveta, y esa es una regla de
    #: negocio (RN-56), no una de forma.
    method: str
    #: Número de transferencia o de cheque. Es lo que se compara con el banco.
    reference: str | None = None
    #: El motivo del movimiento de caja, **armado por el POS** (RN-30). Solo se
    #: usa cuando el método es efectivo, que es el único que escribe en la
    #: gaveta. El backend no lo escribe: una capa que arma la oración tiene que
    #: saber el idioma de la pantalla, y el backend no lo sabe.
    reason: str = ""


class PayablePurchase(BaseModel):
    entry_id: int
    document_number: str | None = None
    document_date: date | None = None
    due_date: date | None = None
    total: float
    paid: float
    balance: float
    #: El piso del tramo de antigüedad en días: 0, 30, 60 o 90 (RF-44). Es un
    #: número y no una etiqueta porque la frase la arma el POS (RN-30).
    bucket: int
    #: Negativo mientras no venza. `None` si no vence.
    days_overdue: int | None = None


class PayableSupplier(BaseModel):
    supplier_id: int
    name: str
    balance: float
    purchases: list[PayablePurchase] = []


class PayableBucket(BaseModel):
    bucket: int
    balance: float


class Payables(BaseModel):
    """Lo que se debe hoy, por proveedor y por compra (RF-44)."""

    #: Contra qué día se calculó la antigüedad. La pone el servidor, como la
    #: hora de una venta: con el reloj del cliente, dos cajas verían tramos
    #: distintos del mismo saldo.
    as_of: date
    total: float
    #: Los cuatro tramos, siempre los cuatro aunque vayan en cero.
    by_bucket: list[PayableBucket] = []
    suppliers: list[PayableSupplier] = []


class PurchaseRateLine(BaseModel):
    #: En porcentaje, como lo dice el documento: 13 y no 0,13.
    tax_rate: float
    base: float
    tax: float


class PurchasesReport(BaseModel):
    """El crédito fiscal del periodo, por tarifa (RF-45)."""

    date_from: str
    date_to: str
    subtotal: float
    tax: float
    total: float
    by_rate: list[PurchaseRateLine] = []


class SupplierPaymentSuccess(BaseModel):
    message: str
    id_payment: int
    #: Lo que queda por pagar de **esa** compra. Es lo que la pantalla vuelve a
    #: pintar sin tener que recargar la lista entera.
    balance: float
    #: La salida de caja, si la hubo. En nulo con cualquier método que no sea
    #: efectivo.
    cash_movement_id: int | None = None
