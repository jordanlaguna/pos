"""Verificación del JWT y control de roles.

El backend emitía tokens pero no los validaba en ningún endpoint: bastaba
conocer una URL para leer o escribir cualquier cosa. Estas dependencias cierran
ese hueco.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.model_user import User
from app.utils.jwt_handler import verify_access_token

# auto_error=False para poder devolver un mensaje propio en español en vez del
# 403 genérico de FastAPI cuando falta la cabecera Authorization.
security = HTTPBearer(auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Devuelve el usuario del token. Lanza 401 si el token falta, venció o
    apunta a un usuario que ya no existe."""

    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o ausente",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or not credentials.credentials:
        raise unauthorized

    payload = verify_access_token(credentials.credentials)
    if not payload:
        raise unauthorized

    user_id = payload.get("id_user")
    if user_id is None:
        raise unauthorized

    user = db.query(User).filter(User.id_user == user_id).first()
    if not user:
        raise unauthorized

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Restringe el endpoint a administradores."""

    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta operación es solo para administradores.",
        )
    return current_user
