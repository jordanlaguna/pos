"""Inventario a fondo (F15, T-1502; migración 023).

Once tablas, todas de la compañía. El kárdex (`stock_movements`) es la
bitácora: una fila por variación, con antes y después, que nunca se edita ni se
borra. La existencia por sucursal (`stock_levels`) es la caché que el kárdex
mantiene, y `products.stock` la suma de las sucursales; los tres se escriben en
la misma transacción y por un solo sitio, `MoveStock`. Si discrepan, manda el
kárdex (RN-98).

Las otras ocho —marcas, lotes, motivos, salidas, traslados y tomas— son las de
T-1503 a T-1507. Van desde ya porque el modelo y la migración tienen que decir
lo mismo (`test_esquema.py`), y una migración partida en dos dejaría dos
esquemas según cuándo la aplique cada quien.

Los índices son los de la migración, con el mismo nombre. Las claves primarias
**sin `index=True`**: estas tablas nacen de la 023 en las bases desplegadas y
de `create_all` en las nuevas, y un `ix_` que solo exista en una de las dos es
justo lo que esa prueba impide.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Computed,
    Date,
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


class Brand(TenantMixin, Base):
    """La marca del producto (RN-104): el fabricante, no la del negocio."""

    __tablename__ = "brands"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_brands_name"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("1"))


class StockLot(TenantMixin, Base):
    """Una partida de un producto con su vencimiento (RN-104).

    Sin tabla de saldos: la existencia de un lote en una sucursal es la suma de
    sus movimientos, que `idx_stock_movements_lot` sirve. Lo que no se usa no se
    paga.
    """

    __tablename__ = "stock_lots"
    __table_args__ = (
        UniqueConstraint("product_id", "code", name="uq_stock_lots"),
        Index("idx_stock_lots_expiry", "company_id", "expires_at"),
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id_product"), nullable=False)
    code = Column(String(40), nullable=False)
    expires_at = Column(Date, nullable=True)
    created_at = Column(DateTime, nullable=False)


class StockMovement(TenantMixin, Base):
    """Una fila del kárdex (RN-98). Lo que dice el dominio en `inventory.Movement`."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        Index("idx_stock_movements_product", "company_id", "product_id", "moved_at"),
        Index("idx_stock_movements_branch", "company_id", "branch_id", "moved_at"),
        Index("idx_stock_movements_source", "source_type", "source_id"),
        # La venta con lotes pregunta «cuánto hay de cada lote de ESTE producto
        # en ESTA sucursal»; un índice solo por lote no la sirve.
        Index("idx_stock_movements_lot", "company_id", "product_id", "branch_id", "lot_id"),
    )

    # BIGINT: es la tabla que más crece —una fila por línea vendida— y la única
    # que nunca se borra.
    id = Column(BigInteger, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id_product"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    #: Uno de `domain/inventory.KINDS`.
    kind = Column(String(16), nullable=False)
    #: Con signo: negativo baja.
    quantity = Column(Integer, nullable=False)
    #: En ESTA sucursal, no el total del producto.
    before_qty = Column(Integer, nullable=False)
    after_qty = Column(Integer, nullable=False)
    #: Con el que se valoró (RN-98).
    unit_cost = Column(Numeric(12, 2), nullable=False, default=0, server_default=text("0"))
    #: El promedio del producto DESPUÉS de este movimiento (RN-103).
    avg_cost_after = Column(Numeric(12, 2), nullable=False, default=0, server_default=text("0"))
    #: RN-104; NULL es «sin lote».
    lot_id = Column(Integer, ForeignKey("stock_lots.id"), nullable=True)
    #: Uno de `domain/inventory.SOURCE_TYPES`, y el id de ese documento.
    source_type = Column(String(16), nullable=False)
    source_id = Column(Integer, nullable=False)
    #: La línea del documento: una línea con lotes deja varios movimientos.
    source_line = Column(Integer, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    #: La pone el servidor.
    moved_at = Column(DateTime, nullable=False)


class StockLevel(TenantMixin, Base):
    """La existencia por sucursal (RN-102): la caché que el kárdex mantiene."""

    __tablename__ = "stock_levels"
    __table_args__ = (
        UniqueConstraint("product_id", "branch_id", name="uq_stock_levels"),
        Index("idx_stock_levels_branch", "company_id", "branch_id"),
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id_product"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=0, server_default=text("0"))


class StockReason(TenantMixin, Base):
    """Por qué salió la mercadería (RN-99). Se desactiva, no se borra."""

    __tablename__ = "stock_reasons"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_stock_reasons_code"),)

    id = Column(Integer, primary_key=True)
    #: 'shrinkage' | 'damage' | 'expired' | 'internal_use' | 'sample' | 'count' | libre.
    code = Column(String(20), nullable=False)
    name = Column(String(80), nullable=False)
    #: 'count' lo usa la toma física y no se desactiva (RN-100).
    is_system = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("1"))


class StockExit(TenantMixin, Base):
    """La salida con motivo (RN-99). Espejo de `stock_entries`, sin proveedor ni impuesto."""

    __tablename__ = "stock_exits"
    __table_args__ = (Index("idx_stock_exits_branch", "company_id", "branch_id", "created_at"),)

    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    reason_id = Column(Integer, ForeignKey("stock_reasons.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    notes = Column(String(255), nullable=True)
    #: 'applied' | 'voided'. En inglés, como planilla: la excepción de §3.9 es
    #: de lo que ya existe, y una tabla nueva no la hereda.
    status = Column(String(20), nullable=False, default="applied", server_default="applied")
    total_cost = Column(Numeric(12, 2), nullable=False, default=0, server_default=text("0"))
    voided_at = Column(DateTime, nullable=True)
    void_reason = Column(String(255), nullable=True)


class StockExitDetail(TenantMixin, Base):
    __tablename__ = "stock_exit_details"
    __table_args__ = (Index("idx_stock_exit_details_exit", "exit_id"),)

    id = Column(Integer, primary_key=True)
    exit_id = Column(Integer, ForeignKey("stock_exits.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id_product"), nullable=False)
    quantity = Column(Integer, nullable=False)
    #: El promedio al salir (RN-99).
    unit_cost = Column(Numeric(12, 2), nullable=False, default=0, server_default=text("0"))
    #: NULL es «sin lote», elegido a propósito (RN-104).
    lot_id = Column(Integer, ForeignKey("stock_lots.id"), nullable=True)


class StockTransfer(TenantMixin, Base):
    """El traslado (RN-102). Sin estado: no se anula, se hace otro al revés."""

    __tablename__ = "stock_transfers"
    __table_args__ = (Index("idx_stock_transfers_company", "company_id", "created_at"),)

    id = Column(Integer, primary_key=True)
    from_branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    to_branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    notes = Column(String(255), nullable=True)


class StockTransferDetail(TenantMixin, Base):
    __tablename__ = "stock_transfer_details"
    __table_args__ = (Index("idx_stock_transfer_details_transfer", "transfer_id"),)

    id = Column(Integer, primary_key=True)
    transfer_id = Column(Integer, ForeignKey("stock_transfers.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id_product"), nullable=False)
    quantity = Column(Integer, nullable=False)
    lot_id = Column(Integer, ForeignKey("stock_lots.id"), nullable=True)


class StockCount(TenantMixin, Base):
    """La toma física (RN-100)."""

    __tablename__ = "stock_counts"
    __table_args__ = (Index("idx_stock_counts_branch", "company_id", "branch_id", "status"),)

    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    #: NULL: toda la sucursal; una raíz incluye sus hijas (RN-100).
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    #: 'open' | 'applied' | 'discarded'.
    status = Column(String(20), nullable=False, default="open", server_default="open")
    opened_by = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    opened_at = Column(DateTime, nullable=False)
    closed_by = Column(Integer, ForeignKey("users.id_user"), nullable=True)
    closed_at = Column(DateTime, nullable=True)
    notes = Column(String(255), nullable=True)


class StockCountLine(TenantMixin, Base):
    __tablename__ = "stock_count_lines"
    __table_args__ = (
        UniqueConstraint("count_id", "product_id", "lot_key", name="uq_stock_count_lines"),
    )

    id = Column(Integer, primary_key=True)
    count_id = Column(Integer, ForeignKey("stock_counts.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id_product"), nullable=False)
    lot_id = Column(Integer, ForeignKey("stock_lots.id"), nullable=True)
    #: En MySQL dos NULL no chocan en un UNIQUE, y «sin lote» es NULL: la
    #: columna generada vuelve 0 ese caso para que la clave sí lo cuide, como
    #: `parent_key` en las categorías.
    lot_key = Column(Integer, Computed("IFNULL(lot_id, 0)", persisted=True), nullable=False)
    #: Lo que decía el sistema AL CONTAR (RN-100).
    system_qty = Column(Integer, nullable=False)
    counted_qty = Column(Integer, nullable=False)
    counted_at = Column(DateTime, nullable=False)
    counted_by = Column(Integer, ForeignKey("users.id_user"), nullable=False)
