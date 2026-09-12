from sqlalchemy import (
    CHAR,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class StockEntry(TenantMixin, Base):
    """Entrada de mercadería al inventario.

    Queda como documento y no como un simple ajuste de stock: cuando dentro de
    tres meses alguien pregunte de dónde salieron 50 unidades, la respuesta es
    esta fila —proveedor, factura, fecha y quién la cargó—. También es lo que
    permite anular una carga hecha dos veces sin adivinar cuánto revertir.
    """

    __tablename__ = "stock_entries"

    # Los dos índices de la migración, declarados también acá (T-915). El de
    # documento es el que sostiene la regla de la factura duplicada: antes de
    # aplicar una entrada se busca si ese número ya se cargó y sigue aplicada.
    __table_args__ = (
        Index("idx_stock_entries_created", "created_at"),
        Index("idx_stock_entries_document", "document_number"),
        # Las dos de F10: el estado de cuenta de un proveedor y lo que vence.
        Index("idx_stock_entries_supplier", "company_id", "supplier_id", "status"),
        Index("idx_stock_entries_due", "company_id", "due_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # Número de factura del proveedor, o el consecutivo del XML de Hacienda.
    document_number = Column(String(100), nullable=True)
    supplier = Column(String(150), nullable=True)
    # 'manual' | 'excel' | 'xml'
    source = Column(String(20), nullable=False, default="manual")
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    # A qué sucursal entró la mercadería. Sin terminal: la bodega no es una caja.
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    notes = Column(String(255), nullable=True)
    # 'aplicada' | 'anulada'
    status = Column(String(20), nullable=False, default="aplicada")
    # Subtotal + impuesto. Existe desde antes de F10 y conserva su significado.
    total_cost = Column(Numeric(12, 2), nullable=False, default=0)

    # ------------------------------------------------------- compra (F10)
    #
    # Lo que convierte una entrada en una compra (RN-52). En nulo sigue siendo
    # una entrada —las que ya existen, las de ajuste— y no genera cuenta por
    # pagar ni crédito fiscal. `supplier` (texto) se conserva para leer el
    # histórico y para que una compra recuerde el nombre aunque el proveedor se
    # desactive.
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    #: La clave de 50 dígitos del comprobante del proveedor, cuando vino de un
    #: XML. `document_number` sigue siendo el consecutivo.
    document_key = Column(CHAR(50), nullable=True)
    #: La fecha del documento, que no es la de carga: una factura del día 28 se
    #: puede estar cargando el 3 del mes siguiente, y el IVA es del 28.
    document_date = Column(Date, nullable=True)
    #: 'cash' | 'credit'
    payment_terms = Column(String(10), nullable=False, default="cash", server_default="cash")
    due_date = Column(Date, nullable=True)
    #: Sin impuesto, y el impuesto, los dos del documento del proveedor (RN-53).
    subtotal = Column(Numeric(12, 2), nullable=False, default=0, server_default=text("0"))
    tax = Column(Numeric(12, 2), nullable=False, default=0, server_default=text("0"))


class StockEntryDetail(TenantMixin, Base):
    __tablename__ = "stock_entry_details"

    # Las líneas se leen por documento, y es lo que recorre la anulación para
    # revertir el stock.
    __table_args__ = (Index("idx_stock_entry_details_entry", "entry_id"),)

    id = Column(Integer, primary_key=True, index=True)
    entry_id = Column(Integer, ForeignKey("stock_entries.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id_product"), nullable=False)
    quantity = Column(Integer, nullable=False)
    # Lo que costó comprarla. No es el precio de venta del producto.
    unit_cost = Column(Numeric(10, 2), nullable=False, default=0)
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)

    # El impuesto de la línea, **tal como lo dice el documento del proveedor**
    # (RN-53): es el crédito fiscal. No se recalcula desde la tarifa del
    # producto, porque lo que se acredita es lo que se pagó.
    tax_rate = Column(Numeric(5, 2), nullable=False, default=0, server_default=text("0"))
    tax_amount = Column(Numeric(12, 2), nullable=False, default=0, server_default=text("0"))
