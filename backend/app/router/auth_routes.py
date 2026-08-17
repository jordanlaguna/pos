"""Entrar al sistema: dos pasos, no uno (plan §3.5, RF-27, RN-24 a RN-26).

    correo + contraseña ─┬─► 1 compañía disponible ──► adentro          (RN-25)
                         └─► 2 o más ──► elegir compañía ──► adentro    (RF-27)

Con membresías, el login dejó de ser una sola operación: autenticar dice *quién*
es la persona, y hasta que no diga *dónde* entra no hay sesión con la que hacer
nada. El estado intermedio dura minutos y no abre ninguna puerta de negocio.

Por qué la lista no se puede pedir con el correo a secas (RN-24): sería un
directorio de los clientes del producto, consultable escribiendo direcciones.
Hay que probar primero que se es esa persona.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.models.model_user import User
from app.schemas.schemas_auth import (
    ChooseCompanyRequest,
    ChooseCompanyResponse,
    CompanyOption,
    InvitationDecision,
    LoginRequest,
    LoginResponse,
)
from app.services import crud_membership, crud_user
from app.utils.auth_dependency import TIPO_SESION, TIPO_TRANSITO, get_db, get_identidad
from app.utils.jwt_handler import create_access_token

router = APIRouter()

#: El token de tránsito dura lo que tarda alguien en leer una lista corta y
#: hacer clic. No es una sesión: es el recibo de haber probado la contraseña.
MINUTOS_DE_TRANSITO = 10


def _opcion(uc, company) -> CompanyOption:
    if uc.aceptada_el is None:
        # Invitación sin aceptar: se ve, pero no abre. No se mira siquiera el
        # estado de la suscripción —lo primero que falta es el consentimiento—.
        puede, motivo = False, "invitacion_pendiente"
    else:
        puede, motivo = crud_membership.puede_entrar(company, uc.rol)

    return CompanyOption(
        pendiente=uc.aceptada_el is None,
        id=company.id,
        afiliado=company.afiliado,
        compania=company.compania,
        nombre=company.nombre,
        estado=company.estado,
        rol=uc.rol,
        puede_entrar=puede,
        motivo=motivo,
    )


def _token_de_sesion(db: Session, user: User, company_id: int, rol: str) -> str:
    """El token de sesión: quién, dónde y con qué rol.

    Sucursal y terminal viajan acá y no en cada petición porque son justo lo que
    el cliente no puede elegir (RN-14). Que estén en el token también es lo que
    permite que un cambio de compañía cambie de sucursal sin nada más.
    """
    sucursal, terminal = crud_membership.sucursal_y_terminal(db, company_id)
    return create_access_token(
        data={
            "id_user": user.id_user,
            "email": user.email,
            "cid": company_id,
            "bid": sucursal,
            "tid": terminal,
            "rol": rol,
            "tipo": TIPO_SESION,
        }
    )


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/login", response_model=LoginResponse)
def login(datos: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Paso 1: autenticar.

    Devuelve el token de sesión directo cuando hay una sola compañía a la que
    entrar —el cajero de un negocio de una sola caja no se entera de que la
    selección existe (RN-25)— y el de tránsito con la lista cuando hay varias.
    """
    user = crud_user.authenticate_user(db, datos.email, datos.password)
    if not user:
        # Mismo error para «no existe» y «contraseña incorrecta»: distinguirlos
        # convierte el login en un verificador de correos registrados.
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    opciones = [_opcion(uc, company) for uc, company in crud_membership.companias_de(db, user.id_user)]
    disponibles = [o for o in opciones if o.puede_entrar]

    # Una sola disponible: se entra sin pantalla intermedia. Se mira
    # `disponibles` y no `opciones` porque tener una compañía bloqueada y una
    # activa tampoco es una elección.
    if len(disponibles) == 1:
        elegida = disponibles[0]
        crud_membership.registrar(
            db,
            user_id=user.id_user,
            company_id=elegida.id,
            accion="login",
            detalle="compañía única",
            ip=_ip(request),
        )
        db.commit()
        return LoginResponse(
            access_token=_token_de_sesion(db, user, elegida.id, elegida.rol),
            tipo=TIPO_SESION,
            user_id=user.id_user,
            company_id=elegida.id,
            companies=opciones,
        )

    # Ninguna disponible tampoco es una elección, pero sí es algo que la persona
    # tiene que poder ver: la lista viaja con el motivo de cada bloqueo (RF-27).
    # El token de tránsito se emite igual para que la pantalla pueda pedirla de
    # nuevo si el dueño paga mientras tanto.
    token = create_access_token(
        data={"id_user": user.id_user, "email": user.email, "tipo": TIPO_TRANSITO},
        expires_delta=timedelta(minutes=MINUTOS_DE_TRANSITO),
    )
    crud_membership.registrar(
        db,
        user_id=user.id_user,
        company_id=None,
        accion="login",
        detalle=f"tránsito, {len(disponibles)} disponibles de {len(opciones)}",
        ip=_ip(request),
    )
    db.commit()
    return LoginResponse(
        access_token=token,
        tipo=TIPO_TRANSITO,
        user_id=user.id_user,
        companies=opciones,
    )


@router.post("/invitation", response_model=list[CompanyOption])
def responder_invitacion(
    datos: InvitationDecision,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_identidad),
):
    """Aceptar o rechazar una invitación a una compañía (T-229).

    Un administrador puede agregar a su compañía a alguien que ya tiene cuenta
    —es la única forma de armar el caso del contador—, pero no puede darle
    acceso a su nombre. Hasta que la persona acepte, la membresía existe y no
    autoriza nada.

    Devuelve la lista completa ya actualizada, para que la pantalla no tenga que
    pedirla otra vez y no pueda quedar mostrando lo de antes.
    """
    if datos.accion not in ("aceptar", "rechazar"):
        raise HTTPException(status_code=400, detail="La acción debe ser 'aceptar' o 'rechazar'.")

    encontrada = crud_membership.membresia(
        db, user.id_user, datos.company_id, incluir_pendientes=True
    )
    if not encontrada:
        raise HTTPException(status_code=404, detail="No encontrada")

    uc, company = encontrada
    if uc.aceptada_el is not None:
        raise HTTPException(status_code=409, detail={"code": "ya_aceptada"})

    if datos.accion == "aceptar":
        uc.aceptada_el = datetime.now().replace(microsecond=0)
    else:
        # Rechazar la desactiva. La compañía deja de aparecer en su lista, y si
        # el administrador vuelve a invitarla, la fila se reactiva pendiente.
        uc.activa = False

    crud_membership.registrar(
        db,
        user_id=user.id_user,
        company_id=company.id,
        accion=f"invitacion_{datos.accion}",
        detalle=f"rol {uc.rol}",
        ip=_ip(request),
    )
    db.commit()

    return [_opcion(m, c) for m, c in crud_membership.companias_de(db, user.id_user)]


@router.get("/companies", response_model=list[CompanyOption])
def mis_companias(db: Session = Depends(get_db), user: User = Depends(get_identidad)):
    """Las compañías de quien trae el token, con su estado y su motivo de bloqueo.

    Sirve para la pantalla de selección y para «cambiar de compañía» desde el
    menú, que es la misma lista vista desde adentro.
    """
    return [_opcion(uc, company) for uc, company in crud_membership.companias_de(db, user.id_user)]


@router.post("/company", response_model=ChooseCompanyResponse)
def elegir_compania(
    datos: ChooseCompanyRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_identidad),
):
    """Paso 2: elegir compañía y recibir la sesión.

    Verifica la membresía **en el servidor**. Mandar un `company_id` cualquiera
    no sirve de nada: si no hay membresía activa, responde 404 —no 403—, porque
    un 403 confirmaría que esa compañía existe.
    """
    encontrada = crud_membership.membresia(db, user.id_user, datos.company_id)
    if not encontrada:
        raise HTTPException(status_code=404, detail="No encontrada")

    uc, company = encontrada
    puede, motivo = crud_membership.puede_entrar(company, uc.rol)
    if not puede:
        # Acá sí es 403 y con motivo: la persona ya demostró que la compañía es
        # suya, así que ocultarle por qué no entra no protege nada y la deja sin
        # saber qué hacer. El motivo es un código; la frase la arma el POS.
        raise HTTPException(status_code=403, detail={"code": motivo})

    crud_membership.registrar(
        db,
        user_id=user.id_user,
        company_id=company.id,
        accion="elegir_compania",
        detalle=f"rol {uc.rol}",
        ip=_ip(request),
    )
    db.commit()

    return ChooseCompanyResponse(
        access_token=_token_de_sesion(db, user, company.id, uc.rol),
        user_id=user.id_user,
        company_id=company.id,
        rol=uc.rol,
    )
