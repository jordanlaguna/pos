from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric
from app.database.database import Base


class StockEntry(Base):
    """Entrada de mercadería al inventario.

    Queda como documento y no como un simple ajuste de stock: cuando dentro de
    tres meses alguien pregunte de dónde salieron 50 unidades, la respuesta es
    esta fila —proveedor, factura, fecha y quién la cargó—. También es lo que
    permite anular una carga hecha dos veces sin adivinar cuánto revertir.
    """

    __tablename__ = "stock_entries"

    id = Column(Integer, primary_key=True, index=True)
    # Número de factura del proveedor, o el consecutivo del XML de Hacienda.
    document_number = Column(String(100), nullable=True)
    supplier = Column(String(150), nullable=True)
    # 'manual' | 'excel' | 'xml'
    source = Column(String(20), nullable=False, default="manual")
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    notes = Column(String(255), nullable=True)
    # 'aplicada' | 'anulada'
    status = Column(String(20), nullable=False, default="aplicada")
    total_cost = Column(Numeric(12, 2), nullable=False, default=0)


class StockEntryDetail(Base):
    __tablename__ = "stock_entry_details"

    id = Column(Integer, primary_key=True, index=True)
    entry_id = Column(Integer, ForeignKey("stock_entries.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id_product"), nullable=False)
    quantity = Column(Integer, nullable=False)
    # Lo que costó comprarla. No es el precio de venta del producto.
    unit_cost = Column(Numeric(10, 2), nullable=False, default=0)
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
