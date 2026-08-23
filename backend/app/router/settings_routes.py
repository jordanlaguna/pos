from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.domain.locale import DEFAULT_LOCALE, effective_locale, normalize_locale
from app.models.model_user import User
from app.schemas.schemas_auth import CompanyLocales, LocaleResponse
from app.schemas.schemas_settings import SettingsResponse, SettingsUpdate
from app.services import crud_membership, crud_session, crud_settings
from app.utils.api_errors import api_error
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


@router.put("/locales", response_model=LocaleResponse)
def update_locales(
    payload: CompanyLocales,
    db: Session = Depends(get_db),
    current: Sesion = Depends(require_admin),
):
    """Los idiomas de la compañía: el de la pantalla y el del documento.

    Son dos ajustes y no uno (RN-29): el del documento es el de la factura, que
    es para el cliente y para Hacienda, así que una compañía costarricense emite
    en español aunque sus cajeros usen el POS en otro idioma.

    Van acá y no en `settings.data` porque viven en columnas de `companies`: el
    de la pantalla hay que leerlo al emitir el token, antes de que exista
    configuración que consultar.

    Devuelve **un token nuevo**, porque el idioma de la pantalla vive en el token
    y el de quien guarda puede haber cambiado: si no eligió uno propio, hereda
    este.
    """
    pantalla = normalize_locale(payload.locale)
    documento = normalize_locale(payload.document_locale)
    for pedido, resuelto in ((payload.locale, pantalla), (payload.document_locale, documento)):
        if resuelto is None:
            raise api_error(400, "unsupported_locale", locale=pedido)

    company = crud_membership.compania(db, current.company_id)
    if company is None:
        raise api_error(404, "membership_not_found")

    company.locale = pantalla
    company.document_locale = documento

    token = crud_session.token_de_sesion(db, current.user, company, current.rol)
    efectivo = effective_locale(current.user.locale, pantalla)

    crud_membership.registrar(
        db,
        user_id=current.id_user,
        company_id=company.id,
        accion="idioma_compania",
        detalle=f"pantalla {pantalla}, documento {documento}",
        ip=None,
    )
    db.commit()

    return LocaleResponse(
        access_token=token,
        locale=efectivo,
        user_locale=current.user.locale,
        document_locale=documento or DEFAULT_LOCALE,
    )
