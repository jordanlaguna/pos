"""Compras y abonos a proveedor (F10).

La compra en sí viaja por `schemas_stock_entry.py`: es la entrada de mercadería
con tres datos más (plan §12.1). Acá va lo que no cabe en ella.
"""

from __future__ import annotations

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


class SupplierPaymentSuccess(BaseModel):
    message: str
    id_payment: int
    #: Lo que queda por pagar de **esa** compra. Es lo que la pantalla vuelve a
    #: pintar sin tener que recargar la lista entera.
    balance: float
    #: La salida de caja, si la hubo. En nulo con cualquier método que no sea
    #: efectivo.
    cash_movement_id: int | None = None
