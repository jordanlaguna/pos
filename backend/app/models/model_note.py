from sqlalchemy import CHAR, Column, DateTime, ForeignKey, Index, Integer, Numeric, String

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class SaleNote(TenantMixin, Base):
    """Una nota por monto sobre un comprobante (RF-77, T-726).

    La ND le sube el monto a líneas de la venta y la NC se lo baja, sin que se
    mueva mercadería. La plata se mueve en el momento: la ND se cobra con su
    medio de pago y la NC sale de la gaveta. Por eso tiene su propia tabla y no
    cuelga de la devolución: una devolución es mercadería que vuelve, y esto no.

    Como la devolución, no modifica la venta: la corrige con un documento propio
    que la referencia.
    """

    __tablename__ = "sale_notes"

    # Por venta es «¿esta factura tiene notas?», que preguntan la NC, la
    # devolución y la anulación; por fecha, el arqueo del turno y los reportes.
    __table_args__ = (
        Index("idx_sale_notes_sale", "sale_id"),
        Index("idx_sale_notes_created", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    terminal_id = Column(Integer, ForeignKey("terminals.id"), nullable=False)
    created_at = Column(DateTime, nullable=False)

    # '02' nota de débito, '03' nota de crédito, y el motivo de Hacienda. Hoy
    # solo '02', corrige monto (`fe_notes.AMOUNT_NOTE_REASONS`).
    document_type = Column(CHAR(2), nullable=False)
    reference_code = Column(CHAR(2), nullable=False)
    reason = Column(String(255), nullable=False)

    # Cómo se cobró la ND. NULL en la NC, que sale de la gaveta como una
    # devolución —sea cual sea el medio con que se pagó la venta—.
    payment_method = Column(String(50), nullable=True)

    subtotal = Column(Numeric(10, 2), nullable=False)
    tax = Column(Numeric(10, 2), nullable=False)
    total = Column(Numeric(10, 2), nullable=False)


class SaleNoteLine(TenantMixin, Base):
    """Una línea de la nota: a qué producto de la venta y por cuánto.

    La tarifa, el código de tarifa, el CABYS y la unidad son **los de la línea
    de la venta** (RN-12, RN-86), copiados al emitir: la nota corrige aquel
    cobro, no uno con la tarifa de hoy.
    """

    __tablename__ = "sale_note_lines"

    __table_args__ = (Index("idx_sale_note_lines_note", "note_id"),)

    id = Column(Integer, primary_key=True, index=True)
    note_id = Column(Integer, ForeignKey("sale_notes.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id_product"), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)
    tax_rate = Column(Numeric(7, 6), nullable=False)
    tax_amount = Column(Numeric(10, 2), nullable=False)
    tax_code = Column(CHAR(2), nullable=True)
    cabys_code = Column(CHAR(13), nullable=True)
    unit_of_measure = Column(String(15), nullable=True)
