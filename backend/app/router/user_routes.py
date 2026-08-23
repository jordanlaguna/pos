"""Usuarios de la compañía en la que se está trabajando.

El login vive en `auth_routes.py` desde F2: dejó de ser una operación sobre
usuarios para ser dos —autenticar y elegir compañía— y no cabía acá.

El rol que devuelven estos endpoints es siempre el de **esta** compañía. La
misma persona puede aparecer como administradora en una y como cajera en otra.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.model_company import UserCompany
from app.schemas.schemas_support import SuscripcionOut
from app.schemas.schemas_user import (
    CurrentUser,
    MembershipGrant,
    RoleUpdate,
    RoleUpdateResponse,
    UserCreate,
    UserResponse,
)
from app.domain.locale import DEFAULT_LOCALE, effective_locale, normalize_locale
from app.services import crud_company, crud_membership, crud_user
from app.utils.api_errors import api_error
from app.utils.auth_dependency import Sesion, get_current_user, get_db, require_admin
from app.utils.tenancy import sin_filtro

router = APIRouter()


#: El nombre para mostrar se resolvía acá; se mudó a `crud_user` cuando el panel
#: de soporte necesitó lo mismo (T-303). Se deja el alias para no tocar las seis
#: llamadas de este archivo.
_display_name = crud_user.display_name


def _cabe_otra_persona(db: Session, company_id: int) -> None:
    """Frena el alta si el plan ya está lleno (RF-12, T-309).

    Va en los dos endpoints que suman gente a una compañía —crear una cuenta y
    sumar una que ya existe— y no en el servicio, porque el servicio lo usan
    también `bootstrap.py` y el alta de compañía, que crean el primer
    administrador: ahí no hay a quién decirle que no cabe.
    """
    cabe, actuales, maximo = crud_company.cabe_otro_usuario(db, company_id)
    if not cabe:
        raise api_error(
            400, "plan_limit_reached", resource="users", current=actuales, max=maximo
        )


@router.get("/me", response_model=CurrentUser)
def read_me(
    db: Session = Depends(get_db),
    sesion: Sesion = Depends(get_current_user),
):
    """Identidad y rol del portador del token, en la compañía de la sesión.

    El frontend lo consulta en cada petición, de modo que revocar o degradar a un
    usuario surte efecto en su siguiente clic, sin esperar a que venza el JWT.
    """
    company = crud_membership.compania(db, sesion.company_id)
    sucursal, terminal = crud_membership.codigos(db, sesion.branch_id, sesion.terminal_id)

    return CurrentUser(
        id_user=sesion.id_user,
        email=sesion.email,
        id_person=sesion.id_person,
        role=sesion.rol,
        name=_display_name(db, sesion.user),
        company_id=sesion.company_id,
        company_name=company.nombre if company else None,
        branch_code=sucursal,
        terminal_code=terminal,
        # Una sesión suplantada no tiene membresías en esta compañía, así que la
        # cuenta daría 0 y el menú ofrecería «cambiar de compañía» a la nada.
        companies_available=(
            0 if sesion.suplantada else len(crud_membership.companias_de(db, sesion.id_user))
        ),
        subscription=(
            SuscripcionOut.model_validate(sesion.suscripcion) if sesion.suscripcion else None
        ),
        impersonated_by=sesion.email if sesion.suplantada else None,
        impersonation_reason=sesion.motivo if sesion.suplantada else None,
        locale=effective_locale(sesion.user.locale, company.locale if company else None),
        user_locale=normalize_locale(sesion.user.locale),
        company_locale=normalize_locale(company.locale if company else None) or DEFAULT_LOCALE,
        document_locale=normalize_locale(company.document_locale if company else None)
        or DEFAULT_LOCALE,
    )


@router.get("/", response_model=list[UserResponse])
def read_users(
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    return [
        UserResponse(
            id_user=u.id_user,
            email=u.email,
            id_person=u.id_person,
            role=uc.rol,
            name=_display_name(db, u),
        )
        for u, uc in crud_user.get_users(db, admin.company_id)
    ]


@router.post("/membership", response_model=UserResponse)
def grant_membership(
    payload: MembershipGrant,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Agrega a esta compañía a alguien que ya tiene cuenta en el sistema.

    Es la operación que hace real el caso del contador: una identidad, varias
    membresías. Crear otra cuenta con el mismo correo no es una alternativa —el
    correo es único global— y tampoco sería lo mismo: serían contraseñas
    distintas que se desincronizan.

    Nota pendiente (T-903): hoy el alta es unilateral. Un administrador puede
    agregar cualquier correo que exista y esa compañía le aparecerá a la otra
    persona en la lista al entrar. No puede hacerle daño —tiene que elegirla
    para que pase algo— pero lo correcto es una invitación que se acepte.
    """
    if payload.role not in crud_user.ROLES:
        raise api_error(400, "invalid_role", role=payload.role)

    user = crud_user.get_user_by_email(db, payload.email)
    if not user:
        raise api_error(404, "account_not_found")

    _cabe_otra_persona(db, admin.company_id)

    membresia = crud_user.grant_membership(db, user.id_user, admin.company_id, payload.role)
    return UserResponse(
        id_user=user.id_user,
        email=user.email,
        id_person=user.id_person,
        role=membresia.rol,
        name=_display_name(db, user),
    )


@router.put("/role/{user_id}", response_model=RoleUpdateResponse)
def update_role(
    user_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Cambia el rol de alguien **en esta compañía**.

    Lo que se modifica es la membresía, no la persona: degradar a un contador en
    un local no lo degrada en los otros dos.
    """
    if payload.role not in crud_user.ROLES:
        raise api_error(400, "invalid_role", role=payload.role)

    encontrado = crud_user.get_user(db, user_id, admin.company_id)
    if not encontrado:
        raise api_error(404, "user_not_found")
    _user, membresia = encontrado

    # Degradar al último administrador dejaría a la compañía sin quien la
    # gestione, y nadie podría volver a otorgar el rol. Se cuenta dentro de esta
    # compañía: que haya administradores en otra no ayuda en nada acá.
    if membresia.rol == "admin" and payload.role != "admin":
        quedan = (
            sin_filtro(
                db.query(UserCompany).filter(
                    UserCompany.company_id == admin.company_id,
                    UserCompany.rol == "admin",
                    UserCompany.activa.is_(True),
                    UserCompany.user_id != user_id,
                )
            )
        ).count()
        if quedan == 0:
            raise api_error(400, "last_admin")

    membresia.rol = payload.role
    db.commit()
    return RoleUpdateResponse(message="role_updated", id_user=user_id)


@router.get("/{user_id}", response_model=UserResponse)
def read_user(
    user_id: int,
    db: Session = Depends(get_db),
    sesion: Sesion = Depends(get_current_user),
):
    if user_id != sesion.id_user and sesion.rol != "admin":
        raise api_error(403, "user_not_yours")

    encontrado = crud_user.get_user(db, user_id, sesion.company_id)
    if not encontrado:
        raise api_error(404, "user_not_found")
    user, membresia = encontrado
    return UserResponse(
        id_user=user.id_user,
        email=user.email,
        id_person=user.id_person,
        role=membresia.rol,
        name=_display_name(db, user),
    )


@router.post("/", response_model=UserResponse)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    _cabe_otra_persona(db, admin.company_id)
    created, membresia = crud_user.create_user(db, user, admin.company_id)
    return UserResponse(
        id_user=created.id_user,
        email=created.email,
        id_person=created.id_person,
        role=membresia.rol,
        name=_display_name(db, created),
    )
