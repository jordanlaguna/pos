"""
Sucursales y terminales (T-608, RF-26).

**Todo es de administrador**, y no solo por prudencia: con eso el bloqueo por
suscripción las alcanza sin tocar nada (plan §4.4), porque vive en
`get_current_user` y se aplica a lo que escribe. Un cajero no abre locales.

Las cuatro escrituras devuelven **el estado completo** —las sucursales, sus
cajas y el cupo del plan— y no solo la fila que tocaron. Una sola forma de
respuesta significa que la pantalla no mezcla lo que tenía con lo que le llega,
que es donde se cuelan los estados a medias; y acá hace falta de verdad, porque
apagar una sucursal apaga sus cajas y crear una consume cupo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.schemas_office import (
    BranchIn,
    BranchUpdate,
    OfficeOut,
    TerminalIn,
    TerminalUpdate,
)
from app.services import crud_office
from app.utils.auth_dependency import Sesion, get_db, require_admin

router = APIRouter()


def _estado(db: Session) -> dict:
    return {
        "branches": crud_office.sucursales(db),
        "terminals": crud_office.terminales(db),
        "quota": crud_office.cupos(db),
    }


@router.get("", response_model=OfficeOut)
def leer(
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Las sucursales de esta compañía, sus cajas y el cupo del plan."""
    return _estado(db)


@router.post("/branches", response_model=OfficeOut)
def crear_sucursal(
    payload: BranchIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    crud_office.crear_sucursal(db, codigo=payload.codigo, nombre=payload.nombre)
    return _estado(db)


@router.put("/branches/{branch_id}", response_model=OfficeOut)
def actualizar_sucursal(
    branch_id: int,
    payload: BranchUpdate,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Renombra, activa o desactiva. El **código no se toca** (ver el esquema)."""
    crud_office.actualizar_sucursal(
        db, branch_id, nombre=payload.nombre, activa=payload.activa
    )
    return _estado(db)


@router.delete("/branches/{branch_id}", response_model=OfficeOut)
def borrar_sucursal(
    branch_id: int,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Borra la que no arrastra nada; con historia responde 409 (RN-7)."""
    crud_office.borrar_sucursal(db, branch_id)
    return _estado(db)


@router.post("/terminals", response_model=OfficeOut)
def crear_terminal(
    payload: TerminalIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    crud_office.crear_terminal(
        db, branch_id=payload.branch_id, codigo=payload.codigo, nombre=payload.nombre
    )
    return _estado(db)


@router.put("/terminals/{terminal_id}", response_model=OfficeOut)
def actualizar_terminal(
    terminal_id: int,
    payload: TerminalUpdate,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    crud_office.actualizar_terminal(
        db, terminal_id, nombre=payload.nombre, activa=payload.activa
    )
    return _estado(db)


@router.delete("/terminals/{terminal_id}", response_model=OfficeOut)
def borrar_terminal(
    terminal_id: int,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    crud_office.borrar_terminal(db, terminal_id)
    return _estado(db)
