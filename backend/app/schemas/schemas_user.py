from pydantic import BaseModel, Field

from app.schemas.schemas_support import SuscripcionOut


class UserCreate(BaseModel):
    email: str
    password: str
    id_person: int | None = None
    role: str = "cajero"


class Login(BaseModel):
    email: str
    password: str


class UserUpdate(BaseModel):
    email: str | None = None
    password: str | None = None
    role: str | None = None


class UserResponse(BaseModel):
    id_user: int
    email: str
    id_person: int | None = None
    role: str = "cajero"
    name: str | None = None

    model_config = {"from_attributes": True}


class CurrentUser(BaseModel):
    """Respuesta de GET /users/me: quién es el portador del token y qué puede hacer.

    `role` es el rol **en esta compañía**, no una propiedad de la persona: la
    misma cuenta puede ser administradora en un negocio y cajera en otro.
    """

    id_user: int
    email: str
    id_person: int | None = None
    role: str
    name: str

    #: Dónde está trabajando esta sesión. El POS los muestra en el menú (T-211):
    #: con varias compañías, saber en cuál se está no es un adorno —es lo que
    #: evita cobrarle una venta al negocio equivocado—.
    company_id: int
    company_name: str | None = None
    branch_code: str | None = None
    terminal_code: str | None = None
    #: Cuántas compañías tiene disponibles. Si es una sola, el POS ni siquiera
    #: muestra la opción de cambiar (RN-25).
    companies_available: int = 1

    #: Los módulos que incluye el plan de esta compañía (RF-40, RN-49). Las tres
    #: claves están siempre, también las apagadas: una clave ausente y una en
    #: `false` no se leen igual del otro lado.
    #:
    #: Vacío por omisión, que es «ninguno». Falla cerrado, igual que todo lo
    #: demás de esta respuesta.
    modules: dict[str, bool] = Field(default_factory=dict)

    #: Idioma de la pantalla y idioma del **documento**, que no son el mismo
    #: (RN-29, T-811). El primero está además en el token, porque tiene que estar
    #: resuelto antes de renderizar; el segundo viaja solo por acá, y eso es a
    #: propósito: se relee en cada petición, así que cambiarlo en Configuración
    #: surte efecto en el siguiente clic y no en el siguiente login.
    locale: str = "es"
    #: Lo que eligió la persona, en nulo si hereda el de la compañía. La pantalla
    #: lo necesita para marcar «como esté configurado», que no es lo mismo que
    #: haber elegido español.
    user_locale: str | None = None
    #: El de la compañía, que es lo que Configuración muestra y edita. No es el
    #: mismo que `locale`: quien eligió uno propio ve el suyo en la pantalla y el
    #: del negocio en Configuración.
    company_locale: str = "es"
    document_locale: str = "es"

    #: El estado de la suscripción, evaluado contra el día de hoy (T-308, RF-10).
    #: Viaja acá y no en el token por lo mismo que `document_locale`: se relee en
    #: cada petición, así que un pago que entra hoy le devuelve el POS al cliente
    #: en el siguiente clic. En el token quedaría congelado hasta el próximo
    #: login, que es lo peor de los dos mundos —bloquea tarde y desbloquea
    #: tarde—.
    subscription: SuscripcionOut | None = None

    #: Correo de quien está suplantando, si esta sesión es un *entrar como*
    #: (RF-8). El POS lo usa para la franja permanente, que es lo que impide
    #: confundir la vista de soporte con la del cliente. Nulo en una sesión
    #: normal.
    impersonated_by: str | None = None
    #: El motivo que dio soporte al entrar, recortado como viene en el token.
    impersonation_reason: str | None = None

    model_config = {"from_attributes": True}


class MembershipGrant(BaseModel):
    """Dar de alta en esta compañía a alguien que ya tiene cuenta.

    Es lo que hace posible el caso del contador que atiende tres locales: una
    sola identidad, tres membresías, tres roles (RN-3). Sin esto, la única forma
    sería crearle tres cuentas con el mismo correo, que es justo lo que T-216
    descartó.
    """

    email: str
    # 'admin' | 'cajero'
    role: str = "cajero"


class RoleUpdate(BaseModel):
    # 'admin' | 'cajero'
    role: str


class RoleUpdateResponse(BaseModel):
    message: str
    id_user: int
