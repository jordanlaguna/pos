"""Verificación del JWT, compañía de la petición y control de roles.

El backend emitía tokens pero no los validaba en ningún endpoint: bastaba
conocer una URL para leer o escribir cualquier cosa. Estas dependencias cierran
ese hueco y, desde F2, son también las que fijan la compañía de la petición.

Un token de sesión lleva `cid` (la compañía) y `rol`. Un token de **tránsito**
—el que devuelve el login cuando la persona tiene varias compañías— no lleva
ninguno de los dos y solo sirve para listar y elegir. Toda ruta de negocio lo
rechaza con 401 (RN-26).

Desde F3 hay dos más, los dos de soporte (RN-4):

* **soporte**: sin compañía, para el panel `/support`. Las pantallas del POS lo
  rechazan por la misma puerta que al de tránsito: sin compañía no hay negocio
  que operar.
* **suplantación**: *entrar como* una compañía (RF-8). Lleva `cid`, dura poco y
  **es de solo lectura**, porque para lo que existe es diagnosticar. La
  membresía no se relee —no hay ninguna— así que en cada petición se vuelve a
  comprobar en la base que quien lo trae siga siendo soporte.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.domain.subscription import Suscripcion, evaluar
from app.models.model_user import User
from app.services import crud_membership
from app.utils import clock
from app.utils.api_errors import api_error, unauthorized
from app.utils.jwt_handler import verify_access_token
from app.utils.tenancy import current_branch, current_company, current_terminal, sin_filtro

# auto_error=False para poder devolver un 401 con código propio en vez del 403
# genérico de FastAPI cuando falta la cabecera Authorization.
security = HTTPBearer(auto_error=False)

#: Tipos de token. El de tránsito dura minutos y no abre ninguna puerta de
#: negocio; el de sesión es el de siempre.
TIPO_SESION = "sesion"
TIPO_TRANSITO = "transito"
#: Los dos de soporte (F3). Ver el encabezado.
TIPO_SOPORTE = "soporte"
TIPO_SUPLANTACION = "suplantacion"

#: Los métodos que cambian algo. Son los que se cierran cuando la suscripción
#: vence: el bloqueo por no pagar es dejar de vender, no dejar de consultar.
METODOS_QUE_ESCRIBEN = ("POST", "PUT", "PATCH", "DELETE")

#: Las rutas que se pueden escribir aunque la sesión sea de solo lectura, con su
#: motivo. La lista es corta y tiene que seguir siéndolo: cada entrada es un
#: agujero en el bloqueo por vencimiento, y `tests/test_suscripcion.py` obliga a
#: que se justifique aquí en vez de en un comentario perdido.
#:
#: Se comparan rutas literales, no plantillas: ninguna de las dos lleva
#: parámetros y el guardián comprueba que sigan existiendo con ese nombre.
ESCRITURA_EN_SOLO_LECTURA: dict[str, str] = {
    "/cash/close": (
        "RN-1: una caja abierta siempre se puede cerrar, en cualquier estado. "
        "Dejar efectivo contado sin poder cuadrarlo es peor que perder una venta."
    ),
    "/auth/locale": (
        "Cambiar de idioma no es operar el negocio, y quien queda en solo "
        "lectura necesita leer el aviso de pago en su idioma."
    ),
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _no_autorizado(code: str = "unauthorized") -> HTTPException:
    """401 con su código. Tres casos distintos y el POS los distingue: el token
    no sirve, no trae compañía, o la membresía dejó de estar activa."""
    return unauthorized(code)


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
    #: El estado de la suscripción de esta compañía, ya evaluado contra el día de
    #: hoy (T-308). Viaja en la sesión porque se necesita en cada petición: es lo
    #: que decide si se puede escribir.
    suscripcion: Suscripcion | None = None
    #: Quién está suplantando, si esto es un *entrar como* (RF-8). Es el id del
    #: usuario de soporte —el mismo que `user`— y está aparte para que el POS
    #: pueda mostrar la franja y para que nadie confunda una sesión suplantada
    #: con una de la compañía.
    suplantada_por: int | None = None
    #: El motivo que dio soporte al entrar. Obligatorio al emitir el token
    #: (RN-4), así que si hay suplantación hay motivo.
    motivo: str | None = None

    @property
    def suplantada(self) -> bool:
        return self.suplantada_por is not None

    @property
    def solo_lectura(self) -> bool:
        """¿Esta sesión puede consultar pero no cambiar nada?

        Dos razones distintas y las dos terminan igual: la suscripción venció y
        se le pasó la gracia, o es soporte mirando de prestado.
        """
        if self.suplantada:
            return True
        return self.suscripcion is not None and not self.suscripcion.puede_vender

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


def _suplantacion(db: Session, user: User, cid: int, payload: dict) -> Sesion:
    """La sesión de un *entrar como* (RF-8, RN-4).

    No hay membresía que releer —soporte no pertenece a ninguna compañía— así
    que lo que se relee es la marca de soporte. Es la misma idea que releer el
    rol en cada petición: quitarle el permiso a alguien tiene que surtir efecto
    en su siguiente clic y no cuando venza el token.
    """
    if not user.is_support:
        # Le quitaron el permiso mientras estaba adentro, o alguien consiguió
        # firmar un token de suplantación sin serlo. En los dos casos, afuera.
        raise api_error(403, "support_only")

    company = crud_membership.compania(db, cid)
    if company is None:
        raise _no_autorizado("membership_inactive")

    return Sesion(
        user=user,
        company_id=cid,
        # Administrador para poder ver todo lo que hay que diagnosticar. No abre
        # la escritura: `solo_lectura` mira `suplantada_por` antes del rol.
        rol="admin",
        branch_id=payload.get("bid"),
        terminal_id=payload.get("tid"),
        suscripcion=evaluar(company.estado, company.vence_el, clock.today()),
        suplantada_por=user.id_user,
        motivo=payload.get("mot"),
    )


def get_current_user(
    request: Request,
    payload: dict = Depends(payload_del_token),
    db: Session = Depends(get_db),
) -> Sesion:
    """La sesión del portador del token. 401 si falta, venció, o no tiene compañía.

    El rol se relee de la membresía en cada petición en vez de creerle al token
    (T-221). Cuesta una consulta y compra que quitarle el permiso a alguien
    surta efecto en su siguiente clic, sin esperar a que venza el JWT —que es lo
    mismo que ya hacía `/users/me`, ahora para todo—.

    Desde F3 también aplica el estado de la suscripción (T-308, RF-10). El
    bloqueo se hace **acá y no en cada ruta** por la misma razón que el filtro de
    compañía se hace en un escuchador de SQLAlchemy: cuarenta sitios que hay que
    acordarse de tocar no son un control de acceso. Se cierra por método —lo que
    escribe— y las dos excepciones están en `ESCRITURA_EN_SOLO_LECTURA` con su
    motivo, no repartidas en comentarios.
    """
    tipo = payload.get("tipo")
    # Soporte no tiene compañía, así que el POS le responde igual que a un token
    # de tránsito: sin compañía no hay negocio que operar (T-302, RN-4).
    if tipo in (TIPO_TRANSITO, TIPO_SOPORTE) or payload.get("cid") is None:
        raise _no_autorizado("no_company_in_token")

    user = _usuario_del_payload(db, payload)
    cid = payload["cid"]

    if tipo == TIPO_SUPLANTACION:
        sesion = _suplantacion(db, user, cid, payload)
    else:
        encontrada = crud_membership.membresia(db, user.id_user, cid)
        if not encontrada:
            # La membresía se desactivó, o el token es de una compañía que ya no
            # le corresponde. En los dos casos deja de ser una sesión válida.
            raise _no_autorizado("membership_inactive")

        uc, company = encontrada
        sesion = Sesion(
            user=user,
            company_id=cid,
            rol=uc.rol,
            branch_id=payload.get("bid"),
            terminal_id=payload.get("tid"),
            suscripcion=evaluar(company.estado, company.vence_el, clock.today(), uc.rol),
        )

    _exigir_escritura(request, sesion)
    return sesion


def _exigir_escritura(request: Request, sesion: Sesion) -> None:
    """Corta las peticiones que cambian algo cuando la sesión es de solo lectura.

    Se mira el método y no lo que hace el endpoint: `POST` que no escribe casi no
    hay, y equivocarse por el lado de bloquear una consulta se nota al primer
    clic, mientras que equivocarse por el otro no se nota nunca.

    El «no» es distinto según el motivo, porque son dos frases distintas: al
    dueño hay que decirle que pague y a soporte que está de visita.
    """
    if not sesion.solo_lectura or request.method not in METODOS_QUE_ESCRIBEN:
        return
    if request.url.path in ESCRITURA_EN_SOLO_LECTURA:
        return

    if sesion.suplantada:
        raise api_error(403, "impersonation_read_only")

    suscripcion = sesion.suscripcion
    raise api_error(
        403,
        "subscription_read_only",
        state=suscripcion.estado if suscripcion else None,
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
        raise api_error(403, "admin_only")
    return sesion


def require_soporte(
    payload: dict = Depends(payload_del_token),
    db: Session = Depends(get_db),
) -> User:
    """Restringe el endpoint al panel de soporte (T-301, RN-4).

    Dos comprobaciones y las dos hacen falta:

    1. El token tiene que ser **de soporte**. Uno de sesión no sirve, aunque su
       dueño sea soporte: la sesión de una compañía no administra la plataforma.
       Tampoco sirve uno de suplantación, que es soporte mirando desde adentro.
    2. La marca `is_support` se relee de la base. Es lo que hace que quitarle el
       permiso a alguien surta efecto en su siguiente clic, y lo que impide que
       un token viejo siga abriendo el panel después de haberlo revocado.

    Devuelve el `User` y no una `Sesion`: una sesión de soporte no tiene
    compañía, ni rol de compañía, ni suscripción. Fingir que los tiene sería
    tener que inventar un `company_id`, que es exactamente lo que RN-4 prohíbe.
    """
    # 403 y no 401 en los dos casos, y a propósito: el token vale, lo que no vale
    # es para esto. Un 401 le diría al POS «volvé a entrar», y volver a entrar no
    # va a convertir a un administrador en soporte (T-302).
    if payload.get("tipo") != TIPO_SOPORTE:
        raise api_error(403, "support_only")

    user = _usuario_del_payload(db, payload)
    if not user.is_support:
        raise api_error(403, "support_only")
    return user
