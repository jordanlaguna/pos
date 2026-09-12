"""El panel de soporte: qué entra y qué sale (F3, RF-5 a RF-9).

Nada de acá lleva frases. `estado`, `aviso` y `motivo` son **códigos** —`activa`,
`en_gracia`, `suspendida`— y la oración la arma el POS con su catálogo (RN-30).
Es el mismo trato que el resto del API, y acá importa más que en ningún otro
lado: el panel es la pantalla que un día habrá que mirar desde un teléfono en
otro idioma.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class PlanOut(BaseModel):
    """Un plan del catálogo. Es lo que el sistema deja hacer, no un precio."""

    id: int
    nombre: str
    precio_mensual: float
    max_sucursales: int
    max_terminales: int
    max_usuarios: int
    factura_electronica: bool
    #: Los módulos que incluye (RN-49, RF-39). Van los tres siempre, también los
    #: apagados: en el formulario una casilla ausente y una sin marcar no se
    #: pueden dibujar igual.
    purchases: bool = False
    accounting: bool = False
    payroll: bool = False


class PlanModulesUpdate(BaseModel):
    """Qué módulos incluye un plan (RF-39).

    Se mandan los tres, no un parche: el formulario tiene tres casillas y manda
    el estado de las tres. Con un parche, desmarcar una y mandar solo las
    marcadas sería indistinguible de no tocarla.

    **Es el plan y no la compañía.** Encender un módulo acá lo enciende para
    todos los clientes de ese plan; para dárselo a uno solo se le cambia el plan
    (`PUT /companies/{id}/subscription`), que es el camino que ya existe.
    """

    purchases: bool
    accounting: bool
    payroll: bool


class UsoOut(BaseModel):
    """Cuánto de su plan usa una compañía (RF-5)."""

    usuarios: int
    terminales: int
    productos: int
    ventas_del_mes: int
    total_del_mes: float
    #: Cuántos más caben. Nulo es «el plan no limita».
    cupo_usuarios: int | None = None
    cupo_terminales: int | None = None


class SuscripcionOut(BaseModel):
    """El estado de la suscripción ya evaluado contra el día de hoy (T-308)."""

    #: El efectivo: `activa` con la fecha pasada sale como `vencida`.
    estado: str
    #: El que está guardado en la base, que puede no ser el efectivo.
    guardado: str
    vence_el: date | None = None
    #: Días hasta el vencimiento. Negativo si ya pasó, nulo si no hay fecha.
    dias: int | None = None
    #: Días de gracia que quedan, contando hoy. 0 = ya no se vende.
    gracia: int = 0
    puede_entrar: bool
    puede_vender: bool
    #: Código del aviso que tiene que mostrar la pantalla, o nulo.
    aviso: str | None = None

    #: Se construye desde `domain.subscription.Suscripcion`, que tiene los mismos
    #: campos: el esquema es la forma en que ese objeto sale por el API.
    model_config = {"from_attributes": True}


class CompanyOut(BaseModel):
    """Una compañía como la ve soporte."""

    id: int
    afiliado: int
    compania: int
    nombre: str
    identificacion: str | None = None
    creada_el: datetime | None = None
    locale: str = "es"
    document_locale: str = "es"
    plan: PlanOut | None = None
    suscripcion: SuscripcionOut
    uso: UsoOut
    #: Correos de sus administradores, para saber a quién escribirle.
    administradores: list[str] = []


class SupportMe(BaseModel):
    """Quién es el de soporte. Sin compañía, porque no tiene (RN-4)."""

    id_user: int
    email: str
    name: str
    is_support: bool = True
    locale: str = "es"


class AdminInicial(BaseModel):
    """El primer administrador de la compañía nueva.

    Si el correo ya existe en el sistema no se crea otra cuenta: se le agrega la
    membresía, y esa nace **pendiente** de que la persona la acepte (T-229).
    """

    email: str
    password: str = Field(min_length=6)
    name: str = "Administrador"
    lastName: str = ""
    secondName: str = ""
    identification: str | None = None
    telephone: str = ""
    birth_date: str = "1990-01-01"


class NewCompany(BaseModel):
    """Alta de compañía (RF-6).

    `afiliado` y `compania` son opcionales: sin ellos, el backend toma el
    siguiente libre —afiliado nuevo para un cliente nuevo, o el próximo número
    de compañía si se manda el afiliado de uno que ya está—. Calcularlo acá evita
    que el formulario tenga que adivinar y que dos altas simultáneas elijan el
    mismo par.
    """

    nombre: str = Field(min_length=1, max_length=160)
    plan_id: int
    admin: AdminInicial
    afiliado: int | None = None
    compania: int | None = None
    identificacion: str | None = None
    estado: str = "prueba"
    vence_el: date | None = None
    locale: str = "es"
    document_locale: str = "es"
    #: La configuración inicial, armada por el POS en el idioma de la compañía.
    #: Trae los textos del documento —el agradecimiento del tiquete y la leyenda
    #: legal—, que nacen vacíos (T-816) y que el backend no puede escribir
    #: porque no tiene catálogo ni sabe en qué idioma (RN-30).
    settings: dict = Field(default_factory=dict)


class NewCompanyResponse(BaseModel):
    """Lo que quedó creado. Se arma antes del commit; ver `crud_company.Alta`."""

    company_id: int
    afiliado: int
    compania: int
    nombre: str
    plan_id: int
    plan_nombre: str
    estado: str
    branch_codigo: str
    terminal_codigo: str
    user_id: int
    email: str
    usuario_nuevo: bool
    #: La membresía quedó pendiente de que la persona la acepte. Pasa cuando el
    #: correo ya existía: no se le puede dar acceso a nombre de otro.
    membresia_pendiente: bool


class SubscriptionUpdate(BaseModel):
    """Cambio de estado, de fecha y —si se manda— de plan (RF-7).

    El plan viaja acá y no en otro endpoint porque una suscripción **es** las
    tres cosas: en qué plan está, en qué estado y hasta cuándo. Sin esto, el
    panel no puede subirle el plan a un cliente que creció.
    """

    estado: str
    vence_el: date | None = None
    plan_id: int | None = None


class ImpersonateRequest(BaseModel):
    """*Entrar como* una compañía (RF-8, RN-4).

    El motivo es obligatorio y con un mínimo que obliga a escribir algo: «x» no
    es un motivo, y una bitácora llena de motivos vacíos es una bitácora que no
    se puede auditar.
    """

    motivo: str = Field(min_length=5, max_length=500)


class ImpersonateResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tipo: str = "suplantacion"
    company_id: int
    company_nombre: str
    #: Cuánto dura la visita. La pantalla lo muestra en la franja.
    minutos: int


class AuditLine(BaseModel):
    """Una línea de la bitácora, con los nombres ya resueltos (RF-9)."""

    id: int
    creado_el: datetime
    user_id: int
    email: str | None = None
    nombre: str | None = None
    company_id: int | None = None
    company_nombre: str | None = None
    accion: str
    detalle: str | None = None
    ip: str | None = None


class AuditPage(BaseModel):
    """Las líneas y las acciones que existen, para armar el filtro."""

    lineas: list[AuditLine] = []
    acciones: list[str] = []
