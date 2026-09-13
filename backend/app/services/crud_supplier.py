"""Proveedores (T-1007, RF-41).

Las consultas van sin filtro escrito a mano: `Supplier` hereda `TenantMixin`, así
que leer devuelve los de la compañía de la sesión y escribir los sella con ella.

Acá no se cuenta nada —`tiene_compras` pregunta si existe una y se detiene en la
primera—, y eso esquiva de paso la trampa que vigila `tests/test_tenancy.py`: la
envoltura de conteo de `Query` no pasa por el filtro automático.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.model_stock_entry import StockEntry
from app.models.model_supplier import Supplier
from app.schemas.schemas_suppliers import SupplierIn, SupplierUpdate


def listar(db: Session, *, incluir_inactivos: bool = False) -> list[Supplier]:
    """Los proveedores de la compañía, por nombre.

    Por omisión solo los activos: la lista sirve para elegir a quién comprarle, y
    quien fue desactivado no es una opción. Los inactivos se piden a propósito,
    desde la pantalla que los administra.
    """
    consulta = db.query(Supplier)
    if not incluir_inactivos:
        consulta = consulta.filter(Supplier.is_active.is_(True))
    return consulta.order_by(Supplier.name).all()


def por_id(db: Session, supplier_id: int) -> Supplier | None:
    return db.query(Supplier).filter(Supplier.id == supplier_id).first()


def por_identificacion(db: Session, identificacion: str) -> Supplier | None:
    """El proveedor con esa cédula, si lo hay.

    Es la consulta que hace el lector de XML para reconocer al emisor sin
    preguntarle nada a nadie (T-1008). Con identificación en nulo no se busca:
    dos proveedores informales no son el mismo.
    """
    if not identificacion:
        return None
    return db.query(Supplier).filter(Supplier.identification == identificacion).first()


def crear(db: Session, datos: SupplierIn, *, ahora: datetime) -> Supplier:
    """Da de alta un proveedor. No hace commit: lo hace quien llamó.

    Así el alta entra en la misma transacción que lo que la motivó —una compra
    desde un XML crea el proveedor y la compra, o no crea ninguno de los dos—.
    """
    proveedor = Supplier(
        name=datos.name.strip(),
        identification_type=datos.identification_type,
        identification=(datos.identification or "").strip() or None,
        email=(datos.email or "").strip() or None,
        phone=(datos.phone or "").strip() or None,
        payment_terms_days=datos.payment_terms_days,
        is_active=True,
        created_at=ahora,
    )
    db.add(proveedor)
    db.flush()
    return proveedor


def actualizar(proveedor: Supplier, datos: SupplierUpdate) -> Supplier:
    """Aplica los cambios sobre la fila. Tampoco hace commit."""
    proveedor.name = datos.name.strip()
    proveedor.identification_type = datos.identification_type
    proveedor.identification = (datos.identification or "").strip() or None
    proveedor.email = (datos.email or "").strip() or None
    proveedor.phone = (datos.phone or "").strip() or None
    proveedor.payment_terms_days = datos.payment_terms_days
    proveedor.is_active = datos.is_active
    return proveedor


def tiene_compras(db: Session, supplier_id: int) -> bool:
    """Si al proveedor ya se le compró algo.

    No sirve para impedir nada —un proveedor no se borra, se desactiva— sino
    para que la pantalla lo diga: desactivar a quien tiene compras con saldo es
    distinto de desactivar a quien se cargó por error.
    """
    return (
        db.query(StockEntry.id).filter(StockEntry.supplier_id == supplier_id).first() is not None
    )
