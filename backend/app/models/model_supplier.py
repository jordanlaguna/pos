"""Proveedores y abonos a proveedor (T-1005, F10).

Las dos heredan `TenantMixin`: un proveedor es de la compañía que le compra, y
dos negocios que le compran al mismo mayorista no tienen por qué verse la
relación.

La **compra** no está acá: es la entrada de mercadería con tres datos más, y
vive en `model_stock_entry.py` (plan §12.1, RN-52).
"""

from sqlalchemy import (
    CHAR,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class Supplier(TenantMixin, Base):
    """A quién se le compra.

    Lleva identificación de Hacienda porque su factura la trae: es lo que
    permite reconocerlo al leer un XML sin preguntarle nada a nadie.
    """

    __tablename__ = "suppliers"

    __table_args__ = (
        # La misma identificación es el mismo proveedor. Admite nulos y en MySQL
        # dos NULL no chocan entre sí, que es justo lo que hace falta: un
        # proveedor informal no tiene cédula y puede haber varios.
        UniqueConstraint("company_id", "identification", name="uq_suppliers_identification"),
        Index("idx_suppliers_name", "company_id", "name"),
    )

    id = Column(Integer, primary_key=True)
    #: 01/02/03/04, la lista de Hacienda. La misma que `companies` (T-621).
    identification_type = Column(CHAR(2), nullable=True)
    identification = Column(String(30), nullable=True)
    name = Column(String(160), nullable=False)
    email = Column(String(160), nullable=True)
    phone = Column(String(30), nullable=True)
    #: Plazo habitual. 0 es contado, y es lo que propone la ficha de una compra
    #: nueva; lo que manda es lo que diga esa compra.
    payment_terms_days = Column(Integer, nullable=False, default=0, server_default=text("0"))
    #: No se borra: se desactiva. Sus compras siguen siendo el respaldo del
    #: crédito fiscal que ya se aplicó.
    #:
    #: `Boolean` y no `Integer`: MySQL lo guarda igual —TINYINT(1)— pero así el
    #: modelo dice lo mismo que la migración, y una instalación nueva no queda
    #: con un esquema distinto de una migrada. Es lo mismo que hizo `plans`.
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at = Column(DateTime, nullable=False)


class SupplierPayment(TenantMixin, Base):
    """Un abono a **una** compra (RN-55).

    No es «a cuenta»: un abono que se reparte entre facturas necesita una regla
    de reparto, y la regla de reparto es lo primero que un proveedor discute.
    Atado al documento, el saldo de cada factura es un hecho y el del proveedor
    es una suma.
    """

    __tablename__ = "supplier_payments"

    __table_args__ = (
        # Se leen por compra —para calcular su saldo— y por proveedor en el
        # tiempo, que es el estado de cuenta.
        Index("idx_supplier_payments_entry", "entry_id"),
        Index("idx_supplier_payments_supplier", "company_id", "supplier_id", "paid_at"),
    )

    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    entry_id = Column(Integer, ForeignKey("stock_entries.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    #: 'cash' | 'transfer' | 'other'
    method = Column(String(20), nullable=False)
    #: Número de transferencia o de cheque. Es lo que se compara con el banco.
    reference = Column(String(100), nullable=True)
    #: La salida de caja, cuando el pago fue en efectivo (RN-56). Sin este
    #: enlace, el asiento de F11 contaría dos veces la misma plata.
    cash_movement_id = Column(Integer, ForeignKey("cash_movements.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    #: La pone el servidor, nunca el cliente. Es la regla 2 de spec §8.
    paid_at = Column(DateTime, nullable=False)
