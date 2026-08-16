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
    """Respuesta de GET /users/me: quién es el portador del token y qué puede hacer."""

    id_user: int
    email: str
    id_person: int | None = None
    role: str
    name: str

    model_config = {"from_attributes": True}


class RoleUpdate(BaseModel):
    # 'admin' | 'cajero'
    role: str


class RoleUpdateResponse(BaseModel):
    message: str
    id_user: int
