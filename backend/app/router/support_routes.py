"""El panel de soporte (F3, RF-5 a RF-9, plan §4).

Cinco cosas: ver los clientes, dar de alta uno nuevo, cambiarle la suscripción,
entrar a diagnosticar y leer la bitácora.

Tres reglas que valen para todo el archivo:

* **Solo soporte.** `require_soporte` en cada endpoint, y no en un `include_router`
  con dependencias globales: una dependencia que se pone una sola vez lejos de
  aquí es una que un día alguien quita sin entender qué sostenía.
* **Sin compañía en el contexto.** La sesión de soporte no tiene compañía
  (RN-4), así que toda consulta a una tabla de negocio va por `crud_support`,
  que las marca con `sin_filtro`. Una consulta directa desde acá fallaría
  cerrado, y está bien que así sea.
* **Todo lo que cambia algo deja línea en la bitácora** (RF-9). Lo comprueba
  `tests/test_soporte.py::test_toda_accion_de_soporte_queda_en_bitacora`, que lee
  el árbol de sintaxis de este archivo: un endpoint nuevo que escriba sin
  registrar tumba `pytest`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.domain.errors import (
    IdentificationTypeRequired,
    InvalidIdentificationType,
    InvalidLocation,
    IssuerIdentificationRequired,
)
from app.domain.fe_issuer import check_issuer_identity
from app.domain.locations import is_blank, location_from_settings
from app.domain.limits import hay_lugar
from app.domain.locale import DEFAULT_LOCALE, effective_locale, normalize_locale
from app.domain.modules import MODULES, Modules
from app.domain.subscription import ESTADOS
from app.models.model_user import User
from app.schemas.schemas_auth import LocaleChoice, LocaleResponse
from app.schemas.schemas_payroll import PayrollRateIn, PayrollRateOut, TaxBracketsIn, TaxBracketsOut
from app.schemas.schemas_support import (
    AuditLine,
    AuditPage,
    CompanyOut,
    ImpersonateRequest,
    ImpersonateResponse,
    IssuerUpdate,
    NewCompany,
    NewCompanyResponse,
    PlanModulesUpdate,
    PlanOut,
    SubscriptionUpdate,
    SupportMe,
    SuscripcionOut,
    UsoOut,
)
from app.services import (
    crud_company,
    crud_membership,
    crud_payroll_rates,
    crud_session,
    crud_support,
    crud_user,
)
from app.utils import clock
from app.utils.api_errors import api_error
from app.utils.auth_dependency import get_db, require_soporte

router = APIRouter()


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _plan_out(plan) -> PlanOut | None:
    if plan is None:
        return None
    return PlanOut(
        id=plan.id,
        nombre=plan.nombre,
        precio_mensual=float(plan.precio_mensual or 0),
        max_sucursales=plan.max_sucursales,
        max_terminales=plan.max_terminales,
        max_usuarios=plan.max_usuarios,
        factura_electronica=bool(plan.factura_electronica),
        **Modules(**{nombre: bool(getattr(plan, nombre)) for nombre in MODULES}).as_dict(),
    )


def _company_out(fila: crud_support.CompaniaConEstado) -> CompanyOut:
    c = fila.company
    return CompanyOut(
        id=c.id,
        afiliado=c.afiliado,
        compania=c.compania,
        nombre=c.nombre,
        identificacion=c.identificacion,
        identification_type=c.identification_type,
        creada_el=c.creada_el,
        locale=normalize_locale(c.locale) or DEFAULT_LOCALE,
        document_locale=normalize_locale(c.document_locale) or DEFAULT_LOCALE,
        plan=_plan_out(fila.plan),
        suscripcion=SuscripcionOut.model_validate(fila.suscripcion),
        uso=UsoOut(**vars(fila.uso)),
        administradores=fila.administradores,
    )


@router.get("/me", response_model=SupportMe)
def quien_soy(db: Session = Depends(get_db), soporte: User = Depends(require_soporte)):
    """Quién trae el token, sin compañía.

    El POS necesita este endpoint porque `/users/me` responde 401 a una sesión de
    soporte —y tiene que responderlo: pedirle la compañía a quien no tiene es la
    definición del estado que RNF-1 prohíbe—.
    """
    return SupportMe(
        id_user=soporte.id_user,
        email=soporte.email,
        name=crud_user.display_name(db, soporte),
        is_support=True,
        locale=effective_locale(soporte.locale, None),
    )


@router.post("/locale", response_model=LocaleResponse)
def elegir_idioma(
    datos: LocaleChoice,
    request: Request,
    db: Session = Depends(get_db),
    soporte: User = Depends(require_soporte),
):
    """El idioma del panel (QA-02), como `/auth/locale` en el POS.

    Hace falta uno propio porque aquel arma un token **de sesión**, con
    compañía, y el de soporte no la tiene (RN-4). Emite un token de soporte
    nuevo: el idioma vive en el token, y sin re-emitirlo el cambio no se vería
    hasta el siguiente login. Nulo no tiene compañía de la que heredar, así que
    es español.
    """
    elegido = None if datos.locale is None else normalize_locale(datos.locale)
    if datos.locale is not None and elegido is None:
        raise api_error(400, "unsupported_locale", locale=datos.locale)

    soporte.locale = elegido
    token = crud_session.token_de_soporte(soporte)
    efectivo = effective_locale(elegido, None)
    crud_membership.registrar(
        db,
        user_id=soporte.id_user,
        company_id=None,
        accion="idioma_usuario",
        detalle=f"{elegido or 'hereda'} → {efectivo}",
        ip=_ip(request),
    )
    db.commit()
    return LocaleResponse(
        access_token=token, locale=efectivo, user_locale=elegido, document_locale=DEFAULT_LOCALE
    )


@router.get("/plans", response_model=list[PlanOut])
def catalogo_de_planes(db: Session = Depends(get_db), soporte: User = Depends(require_soporte)):
    """El catálogo de planes, para el formulario de alta.

    No hay endpoint para crearlos: un plan es una decisión comercial —qué se
    cobra y qué se deja hacer— y se escribe en la base. Lo único que sí se edita
    desde acá son sus **módulos** (RF-39), que son la parte que se vende y se
    deja de vender sin tocar precios ni límites.
    """
    return [_plan_out(p) for p in crud_company.planes(db)]


@router.put("/plans/{plan_id}/modules", response_model=PlanOut)
def cambiar_modulos_del_plan(
    plan_id: int,
    datos: PlanModulesUpdate,
    request: Request,
    db: Session = Depends(get_db),
    soporte: User = Depends(require_soporte),
):
    """Qué módulos incluye un plan (RF-39, T-1003).

    **Alcanza a todos los clientes de ese plan**, y por eso la bitácora anota
    cuántos son: apagar contabilidad en «Comercio» se la apaga a los catorce
    negocios que están ahí, y dentro de seis meses la única forma de entender
    qué pasó ese día es que el número esté escrito.

    Surte efecto en el siguiente clic de cada uno, sin que nadie vuelva a entrar:
    el plan se lee en cada petición que escribe (`require_module`) y no viaja en
    el token, igual que el estado de la suscripción.
    """
    plan = crud_company.plan_por_id(db, plan_id)
    if plan is None:
        raise api_error(404, "plan_not_found", plan_id=plan_id)

    detalle = crud_support.cambiar_modulos(db, plan, Modules(**datos.model_dump()))
    crud_membership.registrar(
        db,
        user_id=soporte.id_user,
        # Sin compañía: el cambio es del catálogo y no de un cliente. La bitácora
        # lo admite —`company_id` es nulo cuando la acción no es sobre ninguna—.
        company_id=None,
        accion="plan_modulos",
        detalle=detalle,
        ip=_ip(request),
    )
    db.commit()
    return _plan_out(plan)


@router.get("/companies", response_model=list[CompanyOut])
def lista_de_companias(
    db: Session = Depends(get_db), soporte: User = Depends(require_soporte)
):
    """Todos los clientes, con afiliado, estado, plan, vencimiento y uso (RF-5)."""
    return [_company_out(fila) for fila in crud_support.companias(db)]


@router.get("/companies/{company_id}", response_model=CompanyOut)
def una_compania(
    company_id: int,
    db: Session = Depends(get_db),
    soporte: User = Depends(require_soporte),
):
    fila = crud_support.una_compania(db, company_id)
    if fila is None:
        raise api_error(404, "company_not_found")
    return _company_out(fila)


@router.post("/companies", response_model=NewCompanyResponse)
def alta_de_compania(
    datos: NewCompany,
    request: Request,
    db: Session = Depends(get_db),
    soporte: User = Depends(require_soporte),
):
    """Dar de alta una compañía con su administrador (RF-6, T-304).

    Queda todo lo que hace falta para vender: la compañía, su sucursal, su
    terminal, su configuración y la membresía del primer administrador. Las seis
    filas las arma `crud_company`, que es el mismo código que usa `bootstrap.py`.

    **La configuración inicial la manda el POS**, incluidos los textos del
    documento. Es la única forma de que nazcan en el idioma de la compañía sin
    que el backend escriba texto para personas (RN-30): el catálogo lo tiene el
    POS y acá no hay ninguno.
    """
    if datos.estado not in ESTADOS:
        raise api_error(400, "invalid_company_state", state=datos.estado)

    for pedido in (datos.locale, datos.document_locale):
        if normalize_locale(pedido) is None:
            raise api_error(400, "unsupported_locale", locale=pedido)

    plan = crud_company.plan_por_id(db, datos.plan_id)
    if plan is None:
        raise api_error(404, "plan_not_found", plan_id=datos.plan_id)

    # Una compañía nace con una sucursal y una caja. Si el plan no las admite, el
    # alta no puede completarse a medias: sería un cliente al que se le cobra un
    # plan en el que no cabe (RF-12).
    for recurso, maximo in (
        ("branches", plan.max_sucursales),
        ("terminals", plan.max_terminales),
        ("users", plan.max_usuarios),
    ):
        if not hay_lugar(0, maximo):
            raise api_error(400, "plan_limit_reached", resource=recurso, current=0, max=maximo)

    # La identificación del emisor, si viene, se guarda limpia y con tipo: va
    # dentro de la clave de cada comprobante (RN-45, T-705).
    identificacion, tipo = _emisor(datos.identificacion, datos.identification_type)
    # Y la ubicación, si viene (RF-73): opcional al dar de alta, pero a medias no.
    _ubicacion_de_alta(datos.settings)

    afiliado = datos.afiliado or crud_company.siguiente_afiliado(db)
    compania = datos.compania or crud_company.siguiente_par(db, afiliado)

    if crud_company.por_par(db, afiliado, compania) is not None:
        # Acá sí es un error, a diferencia de `bootstrap.py`, que reutiliza a
        # propósito: en un formulario, «esa ya existe» es lo que la persona
        # necesita saber antes de que dos clientes compartan una compañía.
        raise api_error(409, "company_already_exists", afiliado=afiliado, compania=compania)

    existente = crud_user.get_user_by_email(db, datos.admin.email)
    if existente is not None and existente.is_support:
        # Soporte no puede ser miembro de una compañía: su login lo manda al
        # panel (RN-4), así que la membresía quedaría creada y sin poder usarse.
        raise api_error(400, "support_cannot_be_member", email=datos.admin.email)

    alta = crud_company.dar_de_alta(
        db,
        crud_company.DatosDeAlta(
            afiliado=afiliado,
            compania=compania,
            nombre=datos.nombre,
            email=datos.admin.email,
            password=datos.admin.password,
            identificacion=identificacion,
            identification_type=tipo,
            plan_id=plan.id,
            estado=datos.estado,
            vence_el=datos.vence_el,
            locale=normalize_locale(datos.locale) or DEFAULT_LOCALE,
            document_locale=normalize_locale(datos.document_locale) or DEFAULT_LOCALE,
            settings=datos.settings,
            nombre_persona=datos.admin.name,
            apellido=datos.admin.lastName,
            segundo_apellido=datos.admin.secondName,
            cedula=datos.admin.identification,
            telefono=datos.admin.telephone,
            nacimiento=datos.admin.birth_date,
        ),
        plan,
    )

    crud_membership.registrar(
        db,
        user_id=soporte.id_user,
        company_id=alta.company_id,
        accion="alta_compania",
        detalle=(
            f"afiliado {alta.afiliado} · compañía {alta.compania} — {alta.nombre}, "
            f"plan {alta.plan_nombre}, estado {alta.estado}, "
            f"administrador {alta.email}"
            f"{' (membresía pendiente)' if alta.membresia_pendiente else ''}"
        ),
        ip=_ip(request),
    )
    db.commit()

    return NewCompanyResponse(
        company_id=alta.company_id,
        afiliado=alta.afiliado,
        compania=alta.compania,
        nombre=alta.nombre,
        plan_id=alta.plan_id,
        plan_nombre=alta.plan_nombre,
        estado=alta.estado,
        branch_codigo=alta.branch_codigo,
        terminal_codigo=alta.terminal_codigo,
        user_id=alta.user_id,
        email=alta.email,
        usuario_nuevo=alta.usuario_nuevo,
        membresia_pendiente=alta.membresia_pendiente,
    )


@router.put("/companies/{company_id}/subscription", response_model=CompanyOut)
def cambiar_suscripcion(
    company_id: int,
    datos: SubscriptionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    soporte: User = Depends(require_soporte),
):
    """Estado, fecha de vencimiento y plan (RF-7, T-305).

    No hay «guardar y avisar»: el efecto es inmediato porque el estado se evalúa
    en cada petición (T-308). Marcar `suspendida` deja al cajero afuera en su
    siguiente clic, y volver a `activa` lo devuelve igual de rápido.
    """
    if datos.estado not in ESTADOS:
        raise api_error(400, "invalid_company_state", state=datos.estado)

    company = crud_company.por_id(db, company_id)
    if company is None:
        raise api_error(404, "company_not_found")

    plan = None
    if datos.plan_id is not None:
        plan = crud_company.plan_por_id(db, datos.plan_id)
        if plan is None:
            raise api_error(404, "plan_not_found", plan_id=datos.plan_id)

    detalle = crud_support.cambiar_suscripcion(
        company, estado=datos.estado, vence_el=datos.vence_el, plan=plan
    )
    crud_membership.registrar(
        db,
        user_id=soporte.id_user,
        company_id=company_id,
        accion="suscripcion",
        detalle=detalle,
        ip=_ip(request),
    )
    db.commit()

    fila = crud_support.una_compania(db, company_id)
    if fila is None:  # pragma: no cover - acaba de existir dos líneas arriba
        raise api_error(404, "company_not_found")
    return _company_out(fila)


@router.put("/companies/{company_id}/issuer", response_model=CompanyOut)
def cambiar_emisor(
    company_id: int,
    datos: IssuerUpdate,
    request: Request,
    db: Session = Depends(get_db),
    soporte: User = Depends(require_soporte),
):
    """Corregir la identificación del emisor (RN-45, T-621).

    La fija soporte al dar de alta y la corrige soporte: el negocio la ve en
    Configuración sin poder editarla, porque su certificado se emite a ella. Y
    queda en bitácora con el antes y el después.
    """
    company = crud_company.por_id(db, company_id)
    if company is None:
        raise api_error(404, "company_not_found")

    identificacion, tipo = _emisor(datos.identificacion, datos.identification_type)
    if identificacion is None or tipo is None:
        raise api_error(400, "identification_required")

    detalle = crud_support.cambiar_emisor(company, identificacion=identificacion, tipo=tipo)
    crud_membership.registrar(
        db,
        user_id=soporte.id_user,
        company_id=company_id,
        accion="emisor",
        detalle=detalle,
        ip=_ip(request),
    )
    db.commit()

    fila = crud_support.una_compania(db, company_id)
    if fila is None:  # pragma: no cover - acaba de existir dos líneas arriba
        raise api_error(404, "company_not_found")
    return _company_out(fila)


def _ubicacion_de_alta(settings: dict | None) -> None:
    """La misma regla que `crud_settings._validar_emisor` para la ubicación."""
    negocio = (settings or {}).get("business")
    ubicacion = negocio.get("location") if isinstance(negocio, dict) else None
    if is_blank(ubicacion):
        return
    try:
        location_from_settings(ubicacion)
    except InvalidLocation as e:
        raise api_error(400, "invalid_location", field=e.field, reason=e.reason) from None


def _emisor(identificacion: str | None, tipo: str | None) -> tuple[str | None, str | None]:
    """La identificación limpia y su tipo, o el «no» que corresponde.

    Vacía es «todavía no se sabe» en el alta —la compañía que no emite no la
    necesita— y se guarda nula.
    """
    if identificacion is None or not identificacion.strip():
        return None, None
    try:
        emisor = check_issuer_identity(identificacion, tipo)
    except IssuerIdentificationRequired as e:
        raise api_error(409, "issuer_identification_required", reason=e.reason) from None
    except InvalidIdentificationType as e:
        raise api_error(
            400, "invalid_identification_type", identification_type=str(e.value)
        ) from None
    except IdentificationTypeRequired:
        raise api_error(400, "identification_type_required") from None
    return emisor.identification, emisor.identification_type


@router.put("/payroll/rates", response_model=PayrollRateOut)
def agregar_tasa_de_planilla(
    datos: PayrollRateIn,
    request: Request,
    db: Session = Depends(get_db),
    soporte: User = Depends(require_soporte),
):
    """Agrega una tasa de planilla con su vigencia (RF-56, T-1204).

    **Alcanza a todas las compañías del país**: las tasas son de la plataforma
    (RN-67). No edita la vigente —una tasa no se edita—: agrega una fila
    posterior a la última del mismo concepto, y desde su `valid_from` la toman
    las corridas que se calculen. Las pagadas no la ven, porque llevan sus
    rubros congelados (RN-66).
    """
    hoy = clock.today()
    fila = crud_payroll_rates.agregar(
        db,
        concept=datos.concept,
        payer=datos.payer,
        value=datos.value,
        valid_from=datos.valid_from,
        source=datos.source,
        today=hoy,
        country=datos.country,
    )
    crud_membership.registrar(
        db,
        user_id=soporte.id_user,
        # Sin compañía: la tasa es del país, no de un cliente.
        company_id=None,
        accion="tasa_planilla",
        detalle=f"{fila.concept}:{fila.payer} = {fila.value} desde {fila.valid_from.isoformat()}",
        ip=_ip(request),
    )
    db.commit()
    return {
        "concept": fila.concept,
        "payer": fila.payer,
        "value": fila.value,
        "valid_from": fila.valid_from,
        "valid_to": fila.valid_to,
        "source": fila.source,
        "verified_at": fila.verified_at,
        "stale": False,
    }


@router.post("/companies/{company_id}/enter", response_model=ImpersonateResponse)
def entrar_como(
    company_id: int,
    datos: ImpersonateRequest,
    request: Request,
    db: Session = Depends(get_db),
    soporte: User = Depends(require_soporte),
):
    """*Entrar como* una compañía para diagnosticar (RF-8, RN-4, T-306).

    Tres cosas hacen que esto sea aceptable y no una puerta trasera:

    1. **Motivo obligatorio**, que queda escrito en la bitácora junto a la fecha
       y al usuario. Sin motivo no se entra.
    2. **Media hora de vigencia.** Es una visita, no una sesión.
    3. **Solo lectura.** El token no permite escribir nada (lo aplica
       `auth_dependency`), porque para lo que existe es mirar. Si hay que
       cambiarle algo a un cliente, se le pide a su administrador o se le crea
       una membresía de verdad, que se ve en la lista de usuarios.

    La franja permanente de la pantalla la pone el POS con `impersonated_by`, que
    viaja en `/users/me`.
    """
    company = crud_company.por_id(db, company_id)
    if company is None:
        raise api_error(404, "company_not_found")

    # El token se arma **antes** del commit: después, SQLAlchemy expira los
    # objetos y leer `company.locale` dispararía una relectura de una tabla que
    # ya no se puede leer sin compañía en el contexto.
    token = crud_session.token_de_suplantacion(db, soporte, company, datos.motivo)
    nombre = company.nombre

    crud_membership.registrar(
        db,
        user_id=soporte.id_user,
        company_id=company_id,
        accion="entrar_como",
        detalle=datos.motivo,
        ip=_ip(request),
    )
    db.commit()

    return ImpersonateResponse(
        access_token=token,
        company_id=company_id,
        company_nombre=nombre,
        minutos=crud_session.MINUTOS_DE_SUPLANTACION,
    )


@router.get("/audit", response_model=AuditPage)
def leer_bitacora(
    db: Session = Depends(get_db),
    soporte: User = Depends(require_soporte),
    company_id: int | None = None,
    accion: str | None = None,
    limite: int = Query(default=crud_support.BITACORA_POR_PAGINA, ge=1),
):
    """La bitácora, filtrable por compañía y por acción (RF-9, T-307).

    Se lee entera desde el panel —incluidos los login de todas las compañías—
    porque es la herramienta con la que se contesta «qué pasó acá»: si solo
    guardara las acciones de soporte, la pregunta que se hace de verdad («por
    qué este cajero no puede entrar») no se podría contestar.
    """
    lineas = crud_support.bitacora(db, company_id=company_id, accion=accion, limite=limite)
    return AuditPage(
        lineas=[AuditLine(**vars(linea)) for linea in lineas],
        acciones=crud_support.acciones(db),
    )


@router.put("/payroll/brackets", response_model=TaxBracketsOut)
def agregar_tramos_de_renta(
    datos: TaxBracketsIn,
    request: Request,
    db: Session = Depends(get_db),
    soporte: User = Depends(require_soporte),
):
    """El juego de tramos y créditos de renta del año siguiente (RF-56, T-1221).

    El decreto sale cada diciembre y rige desde el 1 de enero: soporte lo carga
    con su vigencia sin esperar un despliegue. Entra el juego entero —no se
    edita el vigente— y `GET /payroll/rates?on=` devuelve cada uno desde su
    fecha (RN-67, RN-73).
    """
    hoy = clock.today()
    salida = crud_payroll_rates.agregar_tramos(
        db,
        valid_from=datos.valid_from,
        brackets=[(t.lower, t.upper, t.rate) for t in datos.brackets],
        credits={"child": datos.child_credit, "spouse": datos.spouse_credit},
        source=datos.source,
        today=hoy,
        country=datos.country,
    )
    crud_membership.registrar(
        db,
        user_id=soporte.id_user,
        company_id=None,
        accion="tramos_renta",
        detalle=f"{len(datos.brackets)} tramos desde {datos.valid_from.isoformat()}",
        ip=_ip(request),
    )
    db.commit()
    return salida
