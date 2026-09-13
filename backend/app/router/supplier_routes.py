"""Proveedores (F10, RF-41).

**Es la primera ruta que exige un módulo del plan.** `require_module("purchases")`
va al lado de `require_admin` y no en su lugar: que el plan incluya compras no
dice quién de la compañía puede escribirlas. Y solo corta lo que escribe —un
`GET` pasa aunque el módulo esté apagado—, que es RN-50: bajar de plan deja lo
que ya existe en solo lectura, no lo borra.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models.model_supplier import Supplier
from app.schemas.schemas_suppliers import (
    TIPOS_DE_IDENTIFICACION,
    SupplierIn,
    SupplierOut,
    SupplierUpdate,
)
from app.services import crud_supplier
from app.utils import clock
from app.utils.api_errors import api_error
from app.utils.auth_dependency import Sesion, get_db, require_admin, require_module

router = APIRouter()

#: La dependencia del módulo, construida una vez. Es la misma en las tres rutas.
exige_compras = require_module("purchases")


def _validar(datos: SupplierIn) -> None:
    """Lo que Pydantic no puede decir solo.

    El tipo de identificación tiene que ser uno de los de Hacienda, y no puede
    venir sin su número: un «02» sin cédula jurídica es un dato a medias que
    después no sirve para emitir ni para reconocer al proveedor en un XML.
    """
    if datos.identification_type is not None:
        if datos.identification_type not in TIPOS_DE_IDENTIFICACION:
            raise api_error(
                400, "invalid_identification_type", identification_type=datos.identification_type
            )
        if not (datos.identification or "").strip():
            raise api_error(400, "identification_required")


def _cedula_libre(db: Session, identificacion: str | None, *, excepto: int | None = None) -> None:
    """La misma identificación es el mismo proveedor (RN-52).

    Sin esto, dos fichas del mismo mayorista se reparten sus compras y ninguno de
    los dos saldos es el que se le debe. Lo impide además el UNIQUE de la tabla;
    acá se comprueba para poder decirlo con un código en vez de un 500.
    """
    limpia = (identificacion or "").strip()
    if not limpia:
        return

    existente = crud_supplier.por_identificacion(db, limpia)
    if existente is not None and existente.id != excepto:
        raise api_error(
            400, "supplier_identification_taken", identification=limpia, name=existente.name
        )


def _buscar(db: Session, supplier_id: int) -> Supplier:
    proveedor = crud_supplier.por_id(db, supplier_id)
    if proveedor is None:
        # 404 y no 403: el filtro por compañía ya hizo que el de otra compañía no
        # exista para esta sesión, así que «no está» es la respuesta correcta y la
        # única que no delata que existe en otro lado (RNF-1).
        raise api_error(404, "supplier_not_found", supplier_id=supplier_id)
    return proveedor


@router.get("", response_model=list[SupplierOut])
def listar_proveedores(
    incluir_inactivos: bool = Query(default=False),
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Los proveedores de la compañía (RF-41).

    Sin `require_module`: leer se puede siempre (RN-50). Una compañía que bajó de
    plan tiene que poder seguir consultando a quién le compró.
    """
    return crud_supplier.listar(db, incluir_inactivos=incluir_inactivos)


@router.post("", response_model=SupplierOut)
def crear_proveedor(
    datos: SupplierIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _modulo: Sesion = Depends(exige_compras),
):
    _validar(datos)
    _cedula_libre(db, datos.identification)

    proveedor = crud_supplier.crear(db, datos, ahora=clock.now())
    db.commit()
    db.refresh(proveedor)
    return proveedor


@router.put("/{supplier_id}", response_model=SupplierOut)
def actualizar_proveedor(
    supplier_id: int,
    datos: SupplierUpdate,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _modulo: Sesion = Depends(exige_compras),
):
    """Corregir sus datos, o desactivarlo (RF-41).

    **No se borra.** Sus compras siguen siendo el respaldo del crédito fiscal que
    ya se aplicó, y borrarlo dejaría entradas apuntando a nadie.
    """
    proveedor = _buscar(db, supplier_id)
    _cedula_libre(db, datos.identification, excepto=supplier_id)

    crud_supplier.actualizar(proveedor, datos)
    db.commit()
    db.refresh(proveedor)
    return proveedor
