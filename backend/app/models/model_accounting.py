"""Contabilidad por compañía (T-1101, F11).

Cinco tablas: el catálogo de cuentas, el mapeo que traduce un evento del negocio
a cuentas, los periodos mensuales, y el asiento con sus líneas.

Las cinco heredan `TenantMixin`. El libro de una compañía es lo más privado que
guarda el sistema —está su margen, su deuda y su caja— y no hay una sola consulta
que deba cruzarlo con el de otra.

Lo que **no** está acá es el costo congelado de la línea vendida: vive en
`sale_details.unit_cost`, porque es un dato de la venta y no del libro (RN-63).
"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class Account(TenantMixin, Base):
    """Una cuenta del catálogo.

    La jerarquía está dos veces a propósito: en el texto del código —'1.1.01'
    cuelga de '1.1'— porque es lo que el contador lee, y en `parent_id` porque es
    lo que el programa recorre sin interpretar cadenas.
    """

    __tablename__ = "accounts"

    __table_args__ = (
        # El código es el identificador que usa la gente. Dos cuentas '1.1.01' en
        # la misma compañía harían ambiguo todo asiento que las nombre.
        UniqueConstraint("company_id", "code", name="uq_accounts_code"),
    )

    id = Column(Integer, primary_key=True)
    code = Column(String(20), nullable=False)
    name = Column(String(120), nullable=False)
    #: 'asset' | 'liability' | 'equity' | 'income' | 'cost' | 'expense'.
    #: De esto salen el estado de resultados y el balance general: qué suma dónde
    #: y qué signo tiene su saldo.
    kind = Column(String(10), nullable=False)
    parent_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    #: RN-64: la usa el mapeo, así que no se borra ni se desactiva. No es una
    #: preferencia del usuario: es lo que impide que un asiento automático se
    #: quede sin dónde caer.
    is_system = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    #: Una cuenta con movimientos no se borra nunca —se iría su historia—; se
    #: desactiva y deja de aparecer al escribir un asiento nuevo.
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("1"))


class AccountMapping(TenantMixin, Base):
    """Qué cuenta usa cada papel de cada evento.

    Es la única tabla que el contador ajusta para que los asientos automáticos
    hablen su idioma. Lo que **no** está acá no es un error: cae en «por
    clasificar» y se ve en rojo (RN-59).
    """

    __tablename__ = "account_mappings"

    __table_args__ = (
        # Un papel tiene una cuenta y solo una.
        UniqueConstraint("company_id", "event", "role", name="uq_account_mappings"),
    )

    id = Column(Integer, primary_key=True)
    #: 'sale' | 'return' | 'cash_close' | 'cash_movement' | 'purchase' |
    #: 'supplier_payment' | 'payroll'.
    event = Column(String(40), nullable=False)
    #: El papel que juega la cuenta dentro del evento: 'cash', 'sales_13',
    #: 'vat_payable', 'cogs', 'inventory', 'payables'…
    role = Column(String(40), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)


class AccountingPeriod(TenantMixin, Base):
    """Un mes contable.

    Cerrado es inmutable y no se reabre (RN-61): reabrir es la puerta por donde
    un balance ya entregado deja de coincidir con el libro. Lo que quedó mal se
    ajusta en el periodo abierto, que es lo que un contador hace de todos modos.
    """

    __tablename__ = "accounting_periods"

    __table_args__ = (UniqueConstraint("company_id", "year", "month", name="uq_accounting_periods"),)

    id = Column(Integer, primary_key=True)
    year = Column(SmallInteger, nullable=False)
    #: `SmallInteger` y no el `TINYINT` del boceto del plan: el byte que se
    #: ahorra no paga un tipo que solo existe en MySQL, y el modelo tiene que
    #: decir lo mismo que la migración en las dos instalaciones.
    month = Column(SmallInteger, nullable=False)
    #: 'open' | 'closed'
    status = Column(String(10), nullable=False, default="open", server_default=text("'open'"))
    #: Cerrar es un acto de alguien, no un estado que aparece: queda con quién y
    #: cuándo, y además en `audit_log`.
    closed_at = Column(DateTime, nullable=True)
    closed_by = Column(Integer, nullable=True)


class JournalEntry(TenantMixin, Base):
    """Un asiento.

    `entry_number` es correlativo por compañía y sin huecos, que es lo que pide
    un libro diario y lo que un auditor cuenta.

    Un evento deja un asiento automático y solo uno. Anular una venta no edita el
    suyo: escribe uno de ajuste que lo revierte, y por eso `kind` entra en la
    llave única del origen.
    """

    __tablename__ = "journal_entries"

    __table_args__ = (
        UniqueConstraint("company_id", "entry_number", name="uq_journal_entries_number"),
        UniqueConstraint(
            "company_id",
            "source_type",
            "source_id",
            "kind",
            name="uq_journal_entries_source",
        ),
        # El libro se lee siempre por periodo y en orden de fecha.
        Index("idx_journal_entries_period", "period_id", "entry_date"),
    )

    id = Column(Integer, primary_key=True)
    period_id = Column(Integer, ForeignKey("accounting_periods.id"), nullable=False)
    entry_number = Column(Integer, nullable=False)
    entry_date = Column(Date, nullable=False)
    #: 'auto' | 'manual' | 'adjustment' | 'opening'
    kind = Column(String(12), nullable=False)
    #: 'sale' | 'return' | 'cash_session' | 'cash_movement' | 'stock_entry' |
    #: 'supplier_payment' | 'payroll_run'. NULL en los manuales y en la apertura.
    source_type = Column(String(20), nullable=True)
    source_id = Column(Integer, nullable=True)
    #: El asiento que corrige, cuando es de ajuste (RN-61).
    adjusts_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    description = Column(String(255), nullable=False)
    user_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)


class JournalLine(TenantMixin, Base):
    """Una línea del asiento.

    Débito y crédito en dos columnas y no un monto con signo: es como se lee un
    libro y como se cuadra a ojo. Que una de las dos sea cero lo vigila el
    dominio, con su prueba, y no un CHECK (plan §5).
    """

    __tablename__ = "journal_lines"

    __table_args__ = (
        Index("idx_journal_lines_entry", "entry_id"),
        # El mayor por cuenta: todo lo que movió una cuenta, que es la otra forma
        # en que se lee un libro.
        Index("idx_journal_lines_account", "company_id", "account_id"),
    )

    id = Column(Integer, primary_key=True)
    entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    debit = Column(Numeric(12, 2), nullable=False, default=0, server_default=text("0"))
    credit = Column(Numeric(12, 2), nullable=False, default=0, server_default=text("0"))
    #: En las líneas de IVA. Es lo que hace que el D-104 sea una consulta sobre el
    #: libro y no un cálculo aparte que pueda discrepar (RN-65).
    tax_rate = Column(Numeric(5, 2), nullable=True)
    memo = Column(String(160), nullable=True)
