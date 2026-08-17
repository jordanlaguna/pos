from pydantic import BaseModel


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
