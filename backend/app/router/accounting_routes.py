"""Contabilidad (F11, RF-47).

La activación es de administración y **exige el módulo**: es una escritura, y
RN-50 dice que un módulo apagado impide escribir. La lectura del estado no lo
exige, por la otra mitad de la misma regla: una compañía que bajó de plan tiene
que seguir viendo sus libros, que son su respaldo ante Hacienda.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.schemas.schemas_accounting import (
    Account,
    AccountIn,
    AccountingStatus,
    AccountPatch,
    Activated,
    ActivationIn,
    BalanceSheet,
    Deleted,
    IncomeStatement,
    Journal,
    JournalEntryOut,
    LedgerReport,
    ManualEntryIn,
    Mappings,
    MappingsIn,
    PeriodOut,
    Reclassified,
    ReclassifyIn,
    TrialBalance,
    VatDraft,
)
from app.services import crud_accounting
from app.utils.auth_dependency import Sesion, get_db, require_admin, require_module

router = APIRouter()


@router.get("", response_model=AccountingStatus)
def estado(
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Si esta compañía lleva libros, desde cuándo y con qué plantilla."""
    return crud_accounting.estado(db)


@router.post("/activate", response_model=Activated)
def activar(
    payload: ActivationIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("accounting")),
):
    """Siembra el catálogo, el mapeo, el primer periodo y la apertura (RF-47)."""
    return crud_accounting.activar(db, payload, user_id=admin.user.id_user)


# ---------------------------------------------------------------- el catálogo


@router.get("/accounts", response_model=list[Account])
def cuentas(db: Session = Depends(get_db), admin: Sesion = Depends(require_admin)):
    """El catálogo, ordenado por código (RF-48)."""
    return crud_accounting.cuentas(db)


@router.post("/accounts", response_model=Account)
def crear_cuenta(
    payload: AccountIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("accounting")),
):
    return crud_accounting.crear_cuenta(db, payload)


@router.put("/accounts/{account_id}", response_model=Account)
def actualizar_cuenta(
    account_id: int,
    payload: AccountPatch,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("accounting")),
):
    """Renombrar, y activar o desactivar. Las de sistema no se desactivan (RN-64)."""
    return crud_accounting.actualizar_cuenta(db, account_id, payload)


@router.delete("/accounts/{account_id}", response_model=Deleted)
def borrar_cuenta(
    account_id: int,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("accounting")),
):
    """Solo si nunca tuvo movimientos y no es de sistema (RN-64)."""
    return crud_accounting.borrar_cuenta(db, account_id)


# ------------------------------------------------------------------- el mapeo


@router.get("/mappings", response_model=Mappings)
def mapeo(db: Session = Depends(get_db), admin: Sesion = Depends(require_admin)):
    """Qué cuenta usa cada papel, y qué falta (RF-49)."""
    return crud_accounting.mapeo(db)


@router.put("/mappings", response_model=Mappings)
def guardar_mapeo(
    payload: MappingsIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("accounting")),
):
    """Afecta lo que venga, nunca lo que ya está en el libro (RN-62)."""
    return crud_accounting.guardar_mapeo(db, payload)


# --------------------------------------------------------------- los asientos


@router.get("/entries", response_model=list[JournalEntryOut])
def asientos(
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    kind: str | None = Query(default=None),
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """El libro diario del periodo que se pida (RF-53)."""
    return crud_accounting.asientos(db, year=year, month=month, kind=kind)


@router.post("/entries", response_model=JournalEntryOut)
def crear_asiento(
    payload: ManualEntryIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("accounting")),
):
    """Un asiento manual o de ajuste (RF-51)."""
    return crud_accounting.crear_asiento(db, payload, user_id=admin.user.id_user)


@router.get("/entries/{entry_id:int}", response_model=JournalEntryOut)
def asiento(
    entry_id: int,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Un asiento con sus líneas y el nombre de cada cuenta."""
    return crud_accounting.asiento(db, entry_id)


# --------------------------------------------------------------- los periodos


@router.get("/periods", response_model=list[PeriodOut])
def periodos(db: Session = Depends(get_db), admin: Sesion = Depends(require_admin)):
    """Los meses, del más nuevo al más viejo (RF-52)."""
    return crud_accounting.periodos(db)


@router.post("/periods/{year}/{month}/close", response_model=PeriodOut)
def cerrar_periodo(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("accounting")),
):
    """Cierra el mes, para siempre (RF-52, RN-61).

    La confirmación la pide el POS, que es donde está la persona; acá lo que hay
    que garantizar es que no se deshaga y que quede en bitácora.
    """
    return crud_accounting.cerrar_periodo(db, year, month, sesion=admin)


# -------------------------------------------------------------- los reportes
#
# Los cinco y el D-104, en JSON. **El CSV lo arma el POS** y no esta capa: un CSV
# lleva encabezados, y los encabezados son texto que lee una persona (RN-30). Es
# lo mismo que ya hace la plantilla de importación de inventario, que se sirve
# desde el POS. El plan §13.4 decía `?format=csv` acá; corregido en T-1110.


@router.get("/reports/trial-balance", response_model=TrialBalance)
def balance_de_comprobacion(
    year: int,
    month: int | None = Query(default=None),
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    return crud_accounting.balance_de_comprobacion(db, year, month)


@router.get("/reports/income", response_model=IncomeStatement)
def estado_de_resultados(
    year: int,
    month: int | None = Query(default=None),
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    return crud_accounting.estado_de_resultados(db, year, month)


@router.get("/reports/balance", response_model=BalanceSheet)
def balance_general(
    year: int,
    month: int | None = Query(default=None),
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Acumulado desde que existe el libro, no del mes (ver el servicio)."""
    return crud_accounting.balance_general(db, year, month)


@router.get("/reports/journal", response_model=Journal)
def diario(
    year: int,
    month: int | None = Query(default=None),
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    return crud_accounting.diario(db, year, month)


@router.get("/reports/ledger", response_model=LedgerReport)
def mayor(
    year: int,
    month: int | None = Query(default=None),
    account_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    return crud_accounting.mayor(db, year, month, account_id)


@router.get("/vat", response_model=VatDraft)
def borrador_del_d104(
    year: int,
    month: int | None = Query(default=None),
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """El borrador del D-104 (RF-54, RN-65)."""
    return crud_accounting.borrador_del_d104(db, year, month)


@router.post("/entries/{entry_id}/reclassify", response_model=Reclassified)
def reclasificar(
    entry_id: int,
    payload: ReclassifyIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
    _: None = Depends(require_module("accounting")),
):
    """Mueve a su cuenta lo que cayó en «por clasificar», con un ajuste (RF-49)."""
    return crud_accounting.reclasificar(db, entry_id, payload, user_id=admin.user.id_user)
