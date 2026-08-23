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

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.models.model_user import User
from app.schemas.schemas_auth import (
    ChooseCompanyRequest,
    ChooseCompanyResponse,
    CompanyOption,
    InvitationDecision,
    LocaleChoice,
    LocaleResponse,
    LoginRequest,
    LoginResponse,
)
from app.domain.locale import DEFAULT_LOCALE, effective_locale, normalize_locale
from app.services import crud_membership, crud_session, crud_user
from app.utils.api_errors import api_error
from app.utils.auth_dependency import (
    TIPO_SESION,
    TIPO_SOPORTE,
    TIPO_TRANSITO,
    Sesion,
    get_current_user,
    get_db,
    get_identidad,
)
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
        raise api_error(401, "invalid_credentials")

    if user.is_support:
        # Soporte no elige compañía porque no tiene ninguna (RN-4): su token va
        # sin `cid` y su pantalla es el panel. Se decide acá y no después porque
        # la lista de compañías de soporte estaría vacía y la pantalla de
        # selección le diría «no tiene ninguna disponible», que es cierto y no
        # es lo que hay que hacer con él.
        token = crud_session.token_de_soporte(user)
        crud_membership.registrar(
            db,
            user_id=user.id_user,
            company_id=None,
            accion="login_soporte",
            detalle=None,
            ip=_ip(request),
        )
        db.commit()
        return LoginResponse(access_token=token, tipo=TIPO_SOPORTE, user_id=user.id_user)

    membresias = crud_membership.companias_de(db, user.id_user)
    opciones = [_opcion(uc, company) for uc, company in membresias]
    disponibles = [o for o in opciones if o.puede_entrar]

    # Una sola disponible: se entra sin pantalla intermedia. Se mira
    # `disponibles` y no `opciones` porque tener una compañía bloqueada y una
    # activa tampoco es una elección.
    if len(disponibles) == 1:
        elegida = disponibles[0]
        company = next(c for _, c in membresias if c.id == elegida.id)
        # El token se arma **antes** del commit: después, SQLAlchemy expira los
        # objetos y leer `company.locale` dispararía otra consulta.
        token = crud_session.token_de_sesion(db, user, company, elegida.rol)
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
            access_token=token,
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
        raise api_error(400, "invalid_invitation_action", action=datos.accion)

    encontrada = crud_membership.membresia(
        db, user.id_user, datos.company_id, incluir_pendientes=True
    )
    if not encontrada:
        raise api_error(404, "membership_not_found")

    uc, company = encontrada
    if uc.aceptada_el is not None:
        raise api_error(409, "invitation_already_accepted")

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
        raise api_error(404, "membership_not_found")

    uc, company = encontrada
    puede, motivo = crud_membership.puede_entrar(company, uc.rol)
    if not puede:
        # Acá sí es 403 y con motivo: la persona ya demostró que la compañía es
        # suya, así que ocultarle por qué no entra no protege nada y la deja sin
        # saber qué hacer. El motivo es un código; la frase la arma el POS.
        raise api_error(403, "company_blocked", state=motivo)

    # Igual que en el login: el token se arma antes del commit, porque después
    # leer `company.locale` sería una relectura.
    token = crud_session.token_de_sesion(db, user, company, uc.rol)
    company_id = company.id
    rol = uc.rol

    crud_membership.registrar(
        db,
        user_id=user.id_user,
        company_id=company_id,
        accion="elegir_compania",
        detalle=f"rol {rol}",
        ip=_ip(request),
    )
    db.commit()

    return ChooseCompanyResponse(
        access_token=token,
        user_id=user.id_user,
        company_id=company_id,
        rol=rol,
    )


@router.post("/locale", response_model=LocaleResponse)
def elegir_idioma(
    datos: LocaleChoice,
    request: Request,
    db: Session = Depends(get_db),
    sesion: Sesion = Depends(get_current_user),
):
    """El idioma que prefiere **esta persona** para su sesión (RN-28, T-810).

    Emite un token nuevo, y no es un detalle de implementación: el idioma vive en
    el token (plan §8.4), así que sin re-emitirlo el cambio no se vería hasta el
    siguiente login. Es el mismo camino que «cambiar de compañía» (RF-28).

    `locale` en nulo **borra la preferencia** en vez de guardar «español»: la
    persona vuelve a heredar el de la compañía, que es lo que quiere decir «como
    esté configurado» y no lo mismo que elegir español a mano.
    """
    elegido = None if datos.locale is None else normalize_locale(datos.locale)
    if datos.locale is not None and elegido is None:
        # Un idioma sin catálogo dejaría la pantalla a medio traducir sin avisar.
        raise api_error(400, "unsupported_locale", locale=datos.locale)

    company = crud_membership.compania(db, sesion.company_id)
    if company is None:
        raise api_error(404, "membership_not_found")

    sesion.user.locale = elegido
    token = crud_session.token_de_sesion(db, sesion.user, company, sesion.rol)
    efectivo = effective_locale(elegido, company.locale)

    crud_membership.registrar(
        db,
        user_id=sesion.id_user,
        company_id=company.id,
        accion="idioma_usuario",
        detalle=f"{elegido or 'hereda'} → {efectivo}",
        ip=_ip(request),
    )
    db.commit()

    return LocaleResponse(
        access_token=token,
        locale=efectivo,
        user_locale=elegido,
        document_locale=normalize_locale(company.document_locale) or DEFAULT_LOCALE,
    )
