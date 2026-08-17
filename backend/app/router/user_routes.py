"""Usuarios de la compañía en la que se está trabajando.

El login vive en `auth_routes.py` desde F2: dejó de ser una operación sobre
usuarios para ser dos —autenticar y elegir compañía— y no cabía acá.

El rol que devuelven estos endpoints es siempre el de **esta** compañía. La
misma persona puede aparecer como administradora en una y como cajera en otra.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.model_company import UserCompany
from app.models.model_person import Person
from app.models.model_user import User
from app.schemas.schemas_user import (
    CurrentUser,
    MembershipGrant,
    RoleUpdate,
    RoleUpdateResponse,
    UserCreate,
    UserResponse,
)
from app.services import crud_membership, crud_user
from app.utils.auth_dependency import Sesion, get_current_user, get_db, require_admin
from app.utils.tenancy import sin_filtro

router = APIRouter()


def _display_name(db: Session, user: User) -> str:
    person = sin_filtro(db.query(Person).filter(Person.id_person == user.id_person)).first()
    if person:
        return f"{person.name} {person.lastName}".strip() or user.email
    return user.email


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
        companies_available=len(crud_membership.companias_de(db, sesion.id_user)),
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
        raise HTTPException(status_code=400, detail="El rol debe ser 'admin' o 'cajero'.")

    user = crud_user.get_user_by_email(db, payload.email)
    if not user:
        raise HTTPException(status_code=404, detail="No hay ninguna cuenta con ese correo.")

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
        raise HTTPException(status_code=400, detail="El rol debe ser 'admin' o 'cajero'.")

    encontrado = crud_user.get_user(db, user_id, admin.company_id)
    if not encontrado:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
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
            raise HTTPException(status_code=400, detail="Debe existir al menos un administrador.")

    membresia.rol = payload.role
    db.commit()
    return RoleUpdateResponse(message="Rol actualizado exitosamente", id_user=user_id)


@router.get("/{user_id}", response_model=UserResponse)
def read_user(
    user_id: int,
    db: Session = Depends(get_db),
    sesion: Sesion = Depends(get_current_user),
):
    if user_id != sesion.id_user and sesion.rol != "admin":
        raise HTTPException(status_code=403, detail="No puede consultar este usuario.")

    encontrado = crud_user.get_user(db, user_id, sesion.company_id)
    if not encontrado:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
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
    created, membresia = crud_user.create_user(db, user, admin.company_id)
    return UserResponse(
        id_user=created.id_user,
        email=created.email,
        id_person=created.id_person,
        role=membresia.rol,
        name=_display_name(db, created),
    )
