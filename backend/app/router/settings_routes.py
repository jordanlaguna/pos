from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.model_user import User
from app.schemas.schemas_settings import SettingsResponse, SettingsUpdate
from app.services import crud_settings
from app.utils.auth_dependency import Sesion, get_current_user, require_admin

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=SettingsResponse)
def read_settings(
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    """Configuración vigente.

    La lee cualquier sesión iniciada, no solo el administrador: el cajero
    necesita la moneda para ver los montos y los datos del negocio para imprimir
    el tiquete. Aquí no hay secretos —las credenciales de Hacienda no se
    guardan— así que no hay nada que esconderle.
    """
    return crud_settings.get_settings(db)


@router.put("/", response_model=SettingsResponse)
def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    current: Sesion = Depends(require_admin),
):
    """Reemplaza la configuración completa. Solo administradores."""
    return crud_settings.save_settings(
        db,
        payload.data,
        payload.logo.model_dump() if payload.logo else None,
        payload.keep_logo,
        current.id_user,
    )
