from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class Sale(TenantMixin, Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    sale_number = Column(String(100), nullable=False)
    # Nullable: la mayoría de las ventas de mostrador son de contado y no llevan
    # cliente. Antes era NOT NULL y el cliente WinForms mandaba `client_id = 1`.
    client_id = Column(Integer, ForeignKey("clients.id_client"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    # Dónde y en qué caja se cobró (RN-14). Hacienda los pide en el consecutivo
    # del comprobante, así que sellarlos ahora evita inventarlos en F6.
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    terminal_id = Column(Integer, ForeignKey("terminals.id"), nullable=False)
    total = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)
    tax = Column(Numeric(10, 2), nullable=False)
    payment_method = Column(String(50), nullable=False)
    cash_received = Column(Numeric(10, 2), nullable=False)
    change_given = Column(Numeric(10, 2), nullable=False)
    # DateTime, no Date: sin la hora no se puede saber a qué turno de caja
    # pertenece una venta, y el arqueo deja de tener sentido.
    created_at = Column(DateTime, nullable=False)

    # El consecutivo es de cada compañía. Con el único global, la segunda
    # compañía no habría podido empezar su numeración en 0001.
    __table_args__ = (
        UniqueConstraint("company_id", "sale_number", name="uq_sales_company_number"),
    )
