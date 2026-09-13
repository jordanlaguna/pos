"""Contabilidad: lo que entra y sale por HTTP (F11).

Lo que Pydantic comprueba acá es **forma**, no negocio: que la fecha sea una
fecha y que los montos sean números. Que el asiento balancee, que la plantilla
exista y que el periodo esté abierto son reglas, y viven en el dominio con su
prueba.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.domain.chart import CHART, TEMPLATES

#: Los códigos que la plantilla trae. Se compara contra esto y no contra la base
#: porque al activar **todavía no hay cuentas**: se están creando en ese acto.
CODIGOS_DE_LA_PLANTILLA = frozenset(cuenta.code for cuenta in CHART)


class OpeningLineIn(BaseModel):
    """Un saldo inicial, contra una cuenta **por su código**.

    Por código y no por id porque quien llena esta pantalla todavía no tiene
    cuentas: las está creando en ese mismo acto.
    """

    account_code: str
    debit: float = 0
    credit: float = 0

    @field_validator("account_code")
    @classmethod
    def de_la_plantilla(cls, valor: str) -> str:
        # Forma y no negocio: la pantalla arma el formulario con la misma
        # plantilla que el servidor le dio, así que un código de fuera es un
        # cuerpo mal formado y le toca el 422 de siempre.
        if valor not in CODIGOS_DE_LA_PLANTILLA:
            raise ValueError("account_code")
        return valor


class ActivationIn(BaseModel):
    #: La plantilla de catálogo. Hoy solo hay una, y se pide igual: agregar la de
    #: un taller o la de un restaurante no tiene que cambiar el contrato.
    template: str | None = None
    #: Desde cuándo se llevan libros (RN-60). Lo anterior no se reconstruye.
    start_date: date
    opening: list[OpeningLineIn] | None = None
    #: La frase del asiento de apertura, escrita por quien lo dicta.
    description: str | None = None

    @field_validator("template")
    @classmethod
    def de_las_que_hay(cls, valor: str | None) -> str | None:
        if valor is not None and valor not in TEMPLATES:
            raise ValueError("template")
        return valor


class ChartAccount(BaseModel):
    code: str
    name: str
    kind: str
    is_system: bool


class AccountingStatus(BaseModel):
    active: bool
    template: str | None = None
    start_date: str | None = None
    templates: list[str] = []
    #: La plantilla completa. Va aunque no esté activa: es lo que la pantalla de
    #: activación necesita para ofrecer los saldos iniciales.
    chart: list[ChartAccount] = []


class Activated(AccountingStatus):
    accounts_created: int = 0
    mappings_created: int = 0
    opening_entry_id: int | None = None


# ---------------------------------------------------------------- el catálogo


class Account(BaseModel):
    id: int
    code: str
    name: str
    kind: str
    parent_id: int | None = None
    is_system: bool
    is_active: bool


class AccountIn(BaseModel):
    code: str
    name: str
    #: Uno de los seis. Acá sí lo comprueba Pydantic: no es una regla de negocio
    #: sino el conjunto de valores que la columna admite, y de este tipo salen
    #: los tres estados financieros.
    kind: Literal["asset", "liability", "equity", "income", "cost", "expense"]
    parent_id: int | None = None


class AccountPatch(BaseModel):
    """Lo que se puede cambiar de una cuenta: su nombre y si está activa.

    El código **no** está: es lo que el contador usa para referirse a ella en
    papel y lo que ordena el catálogo. Cambiarlo dejaría los reportes ya
    impresos hablando de otra cuenta.
    """

    name: str | None = None
    is_active: bool | None = None


class Deleted(BaseModel):
    deleted: int


# ------------------------------------------------------------------- el mapeo


class MappingRow(BaseModel):
    event: str
    role: str
    account_id: int | None = None
    account_code: str | None = None
    account_name: str | None = None
    #: Los que caen en «por clasificar» a propósito: no se pintan en rojo,
    #: porque no están mal (plan §13.8).
    unmapped_on_purpose: bool = False


class Mappings(BaseModel):
    mappings: list[MappingRow] = []


class MappingIn(BaseModel):
    event: str
    role: str
    account_id: int


class MappingsIn(BaseModel):
    mappings: list[MappingIn] | None = None


# -------------------------------------------------------------- reclasificar


class ReclassifyIn(BaseModel):
    #: A dónde va el saldo que había caído en «por clasificar».
    account_id: int
    #: La frase de quien reclasifica, si escribe una.
    description: str | None = None


class Reclassified(BaseModel):
    adjustment_entry_id: int


# --------------------------------------------------------------- los asientos


class JournalLineOut(BaseModel):
    account_id: int
    account_code: str
    account_name: str
    debit: float
    credit: float
    #: En porcentaje —13, no 0,13—, como se guarda y como lo pide el D-104.
    tax_rate: float | None = None
    memo: str | None = None


class JournalEntryOut(BaseModel):
    id: int
    entry_number: int
    entry_date: date
    kind: str
    source_type: str | None = None
    source_id: int | None = None
    adjusts_entry_id: int | None = None
    #: Código del evento en los automáticos; frase de quien lo dictó en los
    #: manuales. El POS decide cuál muestra.
    description: str
    user_id: int
    created_at: datetime
    lines: list[JournalLineOut] | None = None
    total: float | None = None


class ManualLineIn(BaseModel):
    account_id: int
    debit: float = 0
    credit: float = 0
    memo: str | None = None


class ManualEntryIn(BaseModel):
    entry_date: date
    #: Obligatoria: es lo único que explica por qué existe el asiento.
    description: str
    lines: list[ManualLineIn] | None = None
    #: Manual o de ajuste. Acá sí lo cierra Pydantic: es forma, no negocio. Los
    #: otros dos tipos —'auto' y 'opening'— no los dicta nadie a mano.
    kind: Literal["manual", "adjustment"] = "manual"
    adjusts_entry_id: int | None = None


# --------------------------------------------------------------- los periodos


class PeriodOut(BaseModel):
    id: int
    year: int
    month: int
    status: str
    closed_at: datetime | None = None
    closed_by: int | None = None
