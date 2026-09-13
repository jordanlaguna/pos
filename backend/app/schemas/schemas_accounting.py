"""Contabilidad: lo que entra y sale por HTTP (F11).

Lo que Pydantic comprueba acá es **forma**, no negocio: que la fecha sea una
fecha y que los montos sean números. Que el asiento balancee, que la plantilla
exista y que el periodo esté abierto son reglas, y viven en el dominio con su
prueba.
"""

from __future__ import annotations

from datetime import date

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
