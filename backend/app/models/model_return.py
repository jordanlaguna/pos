from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class Return(TenantMixin, Base):
    """Devolución de una venta, total o parcial.

    No modifica la venta original: el histórico de facturación queda intacto y
    la devolución se registra como un hecho aparte que la referencia.
    """

    __tablename__ = "returns"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    terminal_id = Column(Integer, ForeignKey("terminals.id"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    reason = Column(String(255), nullable=False)
    total = Column(Numeric(10, 2), nullable=False)


class ReturnDetail(TenantMixin, Base):
    __tablename__ = "return_details"

    id = Column(Integer, primary_key=True, index=True)
    return_id = Column(Integer, ForeignKey("returns.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id_product"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)
