"""Entrar al sistema: autenticar y elegir compañía (plan §3.5).

Los campos que describen un impedimento son **códigos**, no frases: `motivo`
vale `"suspendida"`, no «Su suscripción está suspendida». El backend no escribe
texto para personas —la interfaz se traduce a tres idiomas (RN-30)— y quien arma
la frase es el POS, que además sabe si la está mostrando a un cajero o a un
administrador.
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class CompanyOption(BaseModel):
    """Una compañía a la que la persona podría entrar."""

    id: int
    afiliado: int
    compania: int
    nombre: str
    estado: str
    #: El rol en ESTA compañía. La misma persona puede ser administradora en una
    #: y cajera en otra.
    rol: str
    #: Las bloqueadas se listan igual, con su motivo (RF-27). Una compañía
    #: suspendida que simplemente no aparece se lee como «me borraron la cuenta».
    puede_entrar: bool
    motivo: str | None = None
    #: Invitación sin aceptar (T-229). No se puede entrar hasta aceptarla, y por
    #: eso viaja aparte de `puede_entrar`: la diferencia entre «no podés» y
    #: «todavía no dijiste que sí» es lo único que la pantalla necesita saber
    #: para ofrecer un botón en vez de una explicación.
    pendiente: bool = False


class LoginResponse(BaseModel):
    """Respuesta del paso 1.

    Con una sola compañía disponible viene `tipo="sesion"` y el POS entra
    directo: el cajero no se entera de que la selección existe (RN-25). Con
    varias viene `tipo="transito"` y la lista para elegir.
    """

    access_token: str
    token_type: str = "bearer"
    #: 'sesion' | 'transito'
    tipo: str
    user_id: int
    company_id: int | None = None
    companies: list[CompanyOption] = []


class ChooseCompanyRequest(BaseModel):
    company_id: int


class InvitationDecision(BaseModel):
    """Aceptar o rechazar la invitación a una compañía."""

    company_id: int
    #: 'aceptar' | 'rechazar'
    accion: str


class ChooseCompanyResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tipo: str = "sesion"
    user_id: int
    company_id: int
    rol: str
