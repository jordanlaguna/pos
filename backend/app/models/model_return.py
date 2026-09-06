from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Numeric, String

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class Return(TenantMixin, Base):
    """Devolución de una venta, total o parcial.

    No modifica la venta original: el histórico de facturación queda intacto y
    la devolución se registra como un hecho aparte que la referencia.
    """

    __tablename__ = "returns"

    # Los dos índices de la migración, declarados también acá (T-915). Por venta
    # es «¿esta factura ya se devolvió?», que se pregunta antes de cada
    # devolución; por fecha es el listado de la pantalla.
    __table_args__ = (
        Index("idx_returns_sale", "sale_id"),
        Index("idx_returns_created", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    terminal_id = Column(Integer, ForeignKey("terminals.id"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    reason = Column(String(255), nullable=False)

    # Guardaba SOLO el total. Con una tarifa daba igual —el impuesto se deducía—
    # pero con tarifas mezcladas no hay de dónde deducirlo, así que la
    # devolución no tendría desglose que reimprimir ni con qué cuadrar la caja.
    # NULL es «anterior a la migración 006», donde sí se puede deducir.
    subtotal = Column(Numeric(10, 2), nullable=True)
    tax = Column(Numeric(10, 2), nullable=True)

    total = Column(Numeric(10, 2), nullable=False)


class ReturnDetail(TenantMixin, Base):
    __tablename__ = "return_details"

    __table_args__ = (Index("idx_return_details_return", "return_id"),)

    id = Column(Integer, primary_key=True, index=True)
    return_id = Column(Integer, ForeignKey("returns.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id_product"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)

    # La tarifa con la que se COBRÓ esa línea, copiada de `sale_details` al
    # devolver. No se relee del producto: pudo cambiar desde la venta (RN-12).
    tax_rate = Column(Numeric(7, 6), nullable=True)
    tax_amount = Column(Numeric(10, 2), nullable=True)
