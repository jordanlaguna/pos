from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.model_person import Person
from app.models.model_user import User
from app.schemas.schemas_user import (
    CurrentUser,
    Login,
    RoleUpdate,
    RoleUpdateResponse,
    UserCreate,
    UserResponse,
)
from app.services import crud_user
from app.utils.auth_dependency import get_current_user, require_admin
from app.utils.jwt_handler import create_access_token

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _display_name(db: Session, user: User) -> str:
    person = db.query(Person).filter(Person.id_person == user.id_person).first()
    if person:
        return f"{person.name} {person.lastName}".strip() or user.email
    return user.email


@router.post("/login")
def login(user: Login, db: Session = Depends(get_db)):
    # authenticate_user ya verifica la contraseña; la versión original la volvía
    # a comprobar después, lo que no aportaba nada.
    user_found = crud_user.authenticate_user(db, user.email, user.password)
    if not user_found:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    token = create_access_token(
        data={
            "id_user": user_found.id_user,
            "email": user_found.email,
            "role": user_found.role,
        }
    )

    return {"access_token": token, "token_type": "bearer", "user_id": user_found.id_user}


@router.get("/me", response_model=CurrentUser)
def read_me(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Identidad y rol del portador del token.

    El frontend lo consulta en cada petición, de modo que revocar o degradar a un
    usuario surte efecto en su siguiente clic, sin esperar a que venza el JWT.
    """
    return CurrentUser(
        id_user=current.id_user,
        email=current.email,
        id_person=current.id_person,
        role=current.role,
        name=_display_name(db, current),
    )


@router.get("/", response_model=list[UserResponse])
def read_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    users = crud_user.get_users(db)
    return [
        UserResponse(
            id_user=u.id_user,
            email=u.email,
            id_person=u.id_person,
            role=u.role,
            name=_display_name(db, u),
        )
        for u in users
    ]


@router.put("/role/{user_id}", response_model=RoleUpdateResponse)
def update_role(
    user_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if payload.role not in ("admin", "cajero"):
        raise HTTPException(status_code=400, detail="El rol debe ser 'admin' o 'cajero'.")

    user = db.query(User).filter(User.id_user == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Degradar al último administrador dejaría el sistema sin quien lo gestione,
    # y nadie podría volver a otorgar el rol.
    if user.role == "admin" and payload.role != "admin":
        remaining = db.query(User).filter(User.role == "admin", User.id_user != user_id).count()
        if remaining == 0:
            raise HTTPException(status_code=400, detail="Debe existir al menos un administrador.")

    user.role = payload.role
    db.commit()
    return RoleUpdateResponse(message="Rol actualizado exitosamente", id_user=user_id)


@router.get("/{user_id}", response_model=UserResponse)
def read_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if user_id != current.id_user and current.role != "admin":
        raise HTTPException(status_code=403, detail="No podés consultar este usuario.")

    user = crud_user.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return UserResponse(
        id_user=user.id_user,
        email=user.email,
        id_person=user.id_person,
        role=user.role,
        name=_display_name(db, user),
    )


@router.post("/", response_model=UserResponse)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    created = crud_user.create_user(db, user)
    return UserResponse(
        id_user=created.id_user,
        email=created.email,
        id_person=created.id_person,
        role=created.role,
        name=_display_name(db, created),
    )
