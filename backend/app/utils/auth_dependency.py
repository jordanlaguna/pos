"""Verificación del JWT, compañía de la petición y control de roles.

El backend emitía tokens pero no los validaba en ningún endpoint: bastaba
conocer una URL para leer o escribir cualquier cosa. Estas dependencias cierran
ese hueco y, desde F2, son también las que fijan la compañía de la petición.

Un token de sesión lleva `cid` (la compañía) y `rol`. Un token de **tránsito**
—el que devuelve el login cuando la persona tiene varias compañías— no lleva
ninguno de los dos y solo sirve para listar y elegir. Toda ruta de negocio lo
rechaza con 401 (RN-26).
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.model_user import User
from app.services import crud_membership
from app.utils.jwt_handler import verify_access_token
from app.utils.tenancy import current_branch, current_company, current_terminal, sin_filtro

# auto_error=False para poder devolver un mensaje propio en español en vez del
# 403 genérico de FastAPI cuando falta la cabecera Authorization.
security = HTTPBearer(auto_error=False)

#: Tipos de token. El de tránsito dura minutos y no abre ninguna puerta de
#: negocio; el de sesión es el de siempre.
TIPO_SESION = "sesion"
TIPO_TRANSITO = "transito"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _no_autorizado(detalle: str = "Token inválido o ausente") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalle,
        headers={"WWW-Authenticate": "Bearer"},
    )


@dataclass(frozen=True)
class Sesion:
    """Quién está haciendo la petición, en qué compañía y con qué rol.

    Reemplaza al `User` que devolvían estas dependencias antes. Tuvo que dejar
    de ser un `User` porque el rol ya no es una propiedad de la persona: la
    misma cuenta puede ser administradora en una compañía y cajera en otra, así
    que «el rol de este usuario» no significa nada sin decir dónde.
    """

    user: User
    company_id: int
    rol: str
    #: Dónde está trabajando esta sesión. Salen del token, no del cliente.
    branch_id: int | None = None
    terminal_id: int | None = None

    @property
    def id_user(self) -> int:
        return self.user.id_user

    @property
    def email(self) -> str:
        return self.user.email

    @property
    def id_person(self) -> int:
        return self.user.id_person


async def payload_del_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Valida la firma y deja la compañía fijada en el contexto de la petición.

    Es `async` a propósito, no por gusto: FastAPI corre las dependencias
    síncronas en un hilo aparte, con una **copia** del contexto, y un
    `ContextVar` que se fije ahí no se ve desde el endpoint. Las asíncronas
    corren en la misma tarea que la petición, así que lo que se fija acá sí
    llega hasta las consultas.
    """
    if credentials is None or not credentials.credentials:
        raise _no_autorizado()

    payload = verify_access_token(credentials.credentials)
    if not payload:
        raise _no_autorizado()

    cid = payload.get("cid")
    current_company.set(cid if isinstance(cid, int) else None)
    # Sucursal y terminal viajan juntas con la compañía: si la sesión no dice
    # dónde está, registrar una venta falla en vez de inventar un lugar.
    bid = payload.get("bid")
    tid = payload.get("tid")
    current_branch.set(bid if isinstance(bid, int) else None)
    current_terminal.set(tid if isinstance(tid, int) else None)
    return payload


def _usuario_del_payload(db: Session, payload: dict) -> User:
    user_id = payload.get("id_user")
    if user_id is None:
        raise _no_autorizado()

    # `users` no es tabla de negocio y no se filtra por compañía, pero la marca
    # va escrita: la consulta ocurre en la ventana en que todavía puede no haber
    # compañía, y quien lea esto tiene derecho a saber que es a propósito.
    user = sin_filtro(db.query(User).filter(User.id_user == user_id)).first()
    if not user:
        raise _no_autorizado()
    return user


def get_current_user(
    payload: dict = Depends(payload_del_token),
    db: Session = Depends(get_db),
) -> Sesion:
    """La sesión del portador del token. 401 si falta, venció, o no tiene compañía.

    El rol se relee de la membresía en cada petición en vez de creerle al token
    (T-221). Cuesta una consulta y compra que quitarle el permiso a alguien
    surta efecto en su siguiente clic, sin esperar a que venza el JWT —que es lo
    mismo que ya hacía `/users/me`, ahora para todo—.
    """
    if payload.get("tipo") == TIPO_TRANSITO or payload.get("cid") is None:
        raise _no_autorizado("El token no tiene compañía. Elegí una para continuar.")

    user = _usuario_del_payload(db, payload)
    cid = payload["cid"]

    encontrada = crud_membership.membresia(db, user.id_user, cid)
    if not encontrada:
        # La membresía se desactivó, o el token es de una compañía que ya no le
        # corresponde. En los dos casos deja de ser una sesión válida.
        raise _no_autorizado("La membresía ya no está activa.")

    uc, _company = encontrada
    return Sesion(
        user=user,
        company_id=cid,
        rol=uc.rol,
        branch_id=payload.get("bid"),
        terminal_id=payload.get("tid"),
    )


def get_identidad(
    payload: dict = Depends(payload_del_token),
    db: Session = Depends(get_db),
) -> User:
    """Solo quién es, sin compañía. Para los dos endpoints de selección.

    Acepta tanto el token de tránsito como uno de sesión. Lo segundo es lo que
    permite cambiar de compañía desde el menú sin volver a escribir la
    contraseña (RF-28): un token de sesión prueba la identidad igual de bien que
    el de tránsito, y en ambos casos lo único que se puede ver son las
    membresías propias.
    """
    return _usuario_del_payload(db, payload)


def require_admin(sesion: Sesion = Depends(get_current_user)) -> Sesion:
    """Restringe el endpoint a administradores **de esa compañía**."""

    if sesion.rol != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta operación es solo para administradores.",
        )
    return sesion
