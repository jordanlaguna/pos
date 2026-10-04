"""Lo que entra y sale por las rutas de factura electrónica (F6).

**No hay ningún esquema de salida con el archivo, el PIN ni la contraseña**, y
esa ausencia es el contrato (RF-23, RN-16): no existe el camino. El PIN además
ya no se guarda en ninguna parte desde que la llave vive en Vault.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from app.schemas.schemas_einvoice import ProductionGateOut


class EnvironmentStatusOut(BaseModel):
    """El estado de un ambiente. Lo que la pantalla necesita y nada más."""

    environment: str
    certificate_configured: bool
    certificate_name: str | None = None
    expires_at: datetime | None = None
    #: Días enteros hasta el vencimiento. Negativo si ya pasó.
    days_left: int | None = None
    #: 'missing' | 'expired' | 'expiring' | 'valid'. Es un código y no una
    #: frase: el texto lo arma el POS (RN-30).
    certificate_status: str
    uploaded_at: datetime | None = None
    #: Identificador, no secreto: se muestra a propósito (RN-16).
    atv_user: str | None = None
    atv_configured: bool
    atv_verified_at: datetime | None = None
    #: Certificado vigente **y** credenciales de ATV. Lo decide el dominio para
    #: que la pantalla no tenga una segunda definición de «listo».
    ready: bool


class FeStatusOut(BaseModel):
    """Los **dos** ambientes, siempre, y cuál está en uso.

    Los dos aunque uno no tenga fila: RF-30 pide ver qué le falta a cada uno, y
    con una lista de los configurados, «pruebas no está configurado» sería
    indistinguible de «no vino el dato».
    """

    environments: list[EnvironmentStatusOut]
    #: El ambiente en uso, que vive en la configuración de la compañía y no acá
    #: (plan §7.1): `fe_credentials` guarda credenciales **por** ambiente; cuál
    #: está activo es otro dato.
    active: str
    #: T-713: si ya se puede pasar a producción y, si no, qué falta.
    production_gate: ProductionGateOut


class ActiveEnvironmentIn(BaseModel):
    """A qué ambiente se pasa, y si se confirmó (RF-30, RN-35)."""

    environment: str = Field(min_length=1, max_length=20)
    #: Solo lo exige producción, y lo decide `domain/hacienda.py` —no esta clase—
    #: para que la regla viva en un sitio con prueba. Está en el cuerpo y no en
    #: la pantalla porque esconder un botón no es control de acceso: RN-35 dice
    #: que esto no puede ocurrir por haber tocado un desplegable sin querer.
    confirm: bool = False


class AtvIn(BaseModel):
    """Usuario y contraseña de transmisión.

    El usuario tiene la forma `cpf-01-1234-5678@…` —el dominio de Hacienda vive
    en un solo módulo y no se repite acá— y **no es opcional**: es lo que el IdP
    usa para saber a quién autenticar, así que sin él la contraseña no abre nada.
    """

    user: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=1, max_length=200)


# ------------------------------------------- el arranque de las series (T-616)


class SequenceOut(BaseModel):
    """Una serie: una caja por un tipo de comprobante, en el ambiente en uso."""

    terminal_id: int
    branch_code: str
    branch_name: str
    terminal_code: str
    terminal_name: str
    document_type: str
    #: El último consecutivo emitido; el siguiente sale con uno más. 0 si ninguno.
    last_number: int
    #: El sistema ya emitió con esta serie: desde ahí es suya (RN-38).
    in_use: bool


class SequencesOut(BaseModel):
    environment: str
    items: list[SequenceOut]


class SequenceStartIn(BaseModel):
    """El último consecutivo que emitió el otro sistema (RN-36). Solo sube."""

    terminal_id: int
    document_type: str
    last_number: int


class SequenceStartOut(BaseModel):
    terminal_id: int
    document_type: str
    environment: str
    last_number: int
