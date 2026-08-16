from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric
from app.database.database import Base


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    sale_number = Column(String(100), unique=True, nullable=False)
    # Nullable: la mayoría de las ventas de mostrador son de contado y no llevan
    # cliente. Antes era NOT NULL y el cliente WinForms mandaba `client_id = 1`.
    client_id = Column(Integer, ForeignKey("clients.id_client"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    total = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)
    tax = Column(Numeric(10, 2), nullable=False)
    payment_method = Column(String(50), nullable=False)
    cash_received = Column(Numeric(10, 2), nullable=False)
    change_given = Column(Numeric(10, 2), nullable=False)
    # DateTime, no Date: sin la hora no se puede saber a qué turno de caja
    # pertenece una venta, y el arqueo deja de tener sentido.
    created_at = Column(DateTime, nullable=False)
