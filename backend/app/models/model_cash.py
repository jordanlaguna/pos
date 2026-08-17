from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class CashSession(TenantMixin, Base):
    """Turno de caja: desde que se abre la gaveta hasta que se cuenta y se cierra.

    El monto esperado no se guarda: se calcula al vuelo a partir de la apertura,
    las ventas en efectivo del turno y los movimientos. Guardarlo obligaría a
    recalcularlo con cada venta y quedaría desincronizado a la primera falla.
    """

    __tablename__ = "cash_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    # En qué caja física. Con varias terminales, «el turno de hoy» deja de ser
    # uno solo y el arqueo tiene que saber cuál se está cuadrando.
    terminal_id = Column(Integer, ForeignKey("terminals.id"), nullable=False)
    opened_at = Column(DateTime, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    opening_amount = Column(Numeric(10, 2), nullable=False, default=0)
    # Efectivo contado por el cajero al cerrar. NULL mientras siga abierta.
    closing_amount = Column(Numeric(10, 2), nullable=True)
    status = Column(String(20), nullable=False, default="abierta")
    notes = Column(String(255), nullable=True)


class CashMovement(TenantMixin, Base):
    """Entrada o salida de efectivo que no proviene de una venta.

    No lleva `terminal_id`: pertenece a un turno y el turno ya dice en qué caja
    fue. La redundancia de `company_id` tiene una razón —el filtro automático—;
    esta no tendría ninguna.
    """

    __tablename__ = "cash_movements"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("cash_sessions.id"), nullable=False)
    # 'entrada' | 'salida'
    type = Column(String(10), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    reason = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False)
