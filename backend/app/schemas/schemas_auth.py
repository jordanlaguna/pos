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
    #: 'sesion' | 'transito' | 'soporte'. El último no lleva compañía ni lista:
    #: soporte no pertenece a ninguna y su pantalla es el panel (RN-4).
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


class LocaleChoice(BaseModel):
    """El idioma que elige una persona para su sesión (T-810).

    `None` no es «español»: es «como esté configurada la compañía». Son dos
    intenciones distintas y la diferencia se guarda —la columna admite nulo—,
    porque si el dueño cambia el idioma del negocio, quien no eligió nada tiene
    que seguirlo y quien eligió español tiene que quedarse en español.
    """

    locale: str | None = None


class LocaleResponse(BaseModel):
    """Los dos idiomas después del cambio, y el token que ya los lleva."""

    access_token: str
    token_type: str = "bearer"
    #: El efectivo de la pantalla: lo de la persona, si no lo de la compañía.
    locale: str
    #: Lo que quedó guardado en la persona. Nulo si hereda.
    user_locale: str | None = None
    #: El del documento impreso, que no es el de la pantalla (RN-29).
    document_locale: str = "es"


class CompanyLocales(BaseModel):
    """Los idiomas de la compañía: el de la pantalla y el del documento (T-810, T-811)."""

    locale: str
    document_locale: str
