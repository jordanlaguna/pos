"""Activar la contabilidad de una compañía (T-1107, RF-47, RN-60).

Activar es sembrar: el catálogo de cuentas de la plantilla, el mapeo por
omisión completo, el periodo del mes en que se arranca y —si el contador los
dicta— los saldos iniciales.

**Empieza en una fecha y lo anterior no se reconstruye** (RN-60). Las ventas
viejas no tienen costo congelado ni mapeo vigente, y rehacerlas sería inventar
datos con la cara de un libro. Lo que había antes entra por el asiento de
apertura, que el contador dicta mirando su balance anterior.

**El mapeo se siembra completo**, y esa es la mitad del trabajo. Un papel sin
cuenta no rompe nada —cae en 1.9.99, que para eso está— pero le deja al contador
un saldo en rojo el primer día por algo que el sistema sabía desde antes de
empezar.

**Activar dos veces no se permite.** No es por prolijidad: la segunda vez
volvería a sembrar sobre un libro con movimiento y podría cambiar el mapeo bajo
los asientos que ya existen, que es exactamente lo que RN-62 prohíbe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.application.ports.accounting import (
    AccountingSettings,
    AccountRepository,
    MappingRepository,
    PeriodRepository,
)
from app.application.ports.clock import Clock
from app.application.ports.ledger import JournalWriter
from app.application.ports.repositories import UnitOfWork
from app.domain.chart import CHART, TEMPLATES, default_mapping
from app.domain.errors import DomainError
from app.domain.ledger import OPENING, JournalEntry, Line
from app.domain.money import Money


class AlreadyActive(DomainError):
    """La compañía ya lleva libros."""

    def __init__(self) -> None:
        super().__init__("la contabilidad ya está activada")


class UnknownTemplate(DomainError):
    def __init__(self, template: str) -> None:
        super().__init__(f"no hay plantilla de catálogo llamada {template!r}")
        self.template = template


class UnknownAccountCode(DomainError):
    """Un saldo inicial contra una cuenta que la plantilla no trae."""

    def __init__(self, code: str) -> None:
        super().__init__(f"no hay cuenta con código {code!r}")
        self.code = code


@dataclass(frozen=True)
class OpeningLine:
    """Un saldo inicial, contra una cuenta **por su código**.

    Por código y no por id porque quien llena esta pantalla todavía no tiene
    cuentas: las está creando en este mismo acto, y lo único que conoce es la
    plantilla.
    """

    account_code: str
    debit: Money = field(default_factory=Money.zero)
    credit: Money = field(default_factory=Money.zero)

    @property
    def is_empty(self) -> bool:
        return self.debit.is_zero and self.credit.is_zero


@dataclass(frozen=True)
class ActivationRequest:
    template: str
    start_date: date
    user_id: int
    opening: tuple[OpeningLine, ...] = ()
    #: La frase del asiento de apertura, si quien lo dicta escribe una. Es texto
    #: de una persona, no del servidor (RN-30).
    description: str = ""


@dataclass(frozen=True)
class Activated:
    accounts_created: int
    mappings_created: int
    opening_entry_id: int | None


class ActivateAccounting:
    def __init__(
        self,
        *,
        accounts: AccountRepository,
        mappings: MappingRepository,
        periods: PeriodRepository,
        settings: AccountingSettings,
        journal: JournalWriter,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._accounts = accounts
        self._mappings = mappings
        self._periods = periods
        self._settings = settings
        self._journal = journal
        self._uow = uow
        self._clock = clock

    def __call__(self, request: ActivationRequest) -> Activated:
        if self._settings.accounting().get("active"):
            raise AlreadyActive()
        if request.template not in TEMPLATES:
            raise UnknownTemplate(request.template)

        with self._uow:
            cuentas = self._sembrar_cuentas()
            mapeadas = self._sembrar_mapeo(cuentas)

            # El mes en que se arranca. Los siguientes nacen solos con su primer
            # asiento; este se crea acá porque la apertura tiene que caer adentro.
            if self._periods.get(request.start_date.year, request.start_date.month) is None:
                self._periods.create(request.start_date.year, request.start_date.month)

            apertura = self._apertura(request, cuentas)

            self._settings.save_accounting(
                {
                    "active": True,
                    "template": request.template,
                    "start_date": request.start_date.isoformat(),
                    "activated_at": self._clock.now().isoformat(),
                    "activated_by": request.user_id,
                }
            )
            self._uow.commit()

        return Activated(
            accounts_created=self._creadas,
            mappings_created=mapeadas,
            opening_entry_id=apertura,
        )

    # ------------------------------------------------------------ por dentro

    def _sembrar_cuentas(self) -> dict[str, int]:
        """Crea lo que falte de la plantilla y devuelve `código → id`.

        Lo que ya existe **no se toca**: una compañía puede haber quedado con
        cuentas de un intento anterior que falló a mitad, y volver a crearlas
        chocaría contra el único de (compañía, código).
        """
        cuentas = {fila.code: fila.id for fila in self._accounts.all()}
        self._creadas = 0
        for plantilla in CHART:
            if plantilla.code in cuentas:
                continue
            cuentas[plantilla.code] = self._accounts.create(
                code=plantilla.code,
                name=plantilla.name,
                kind=plantilla.kind,
                # La jerarquía va por el texto del código y la plantilla es
                # plana: las de agrupación las crea el contador si las quiere.
                parent_id=None,
                is_system=plantilla.is_system,
            )
            self._creadas += 1
        return cuentas

    def _sembrar_mapeo(self, cuentas: dict[str, int]) -> int:
        """Asigna cuenta a cada papel que no tenga una.

        Lo que ya estuviera mapeado se respeta, por RN-62: cambiar el mapeo
        afecta lo que venga, y acá no hay ningún motivo para pisarlo.
        """
        ya = {(evento, papel) for evento, papel, _ in self._mappings.all()}
        puestas = 0
        for (evento, papel), codigo in default_mapping().items():
            if (evento, papel) in ya:
                continue
            self._mappings.set(event=evento, role=papel, account_id=cuentas[codigo])
            puestas += 1
        return puestas

    def _apertura(
        self, request: ActivationRequest, cuentas: dict[str, int]
    ) -> int | None:
        """El asiento de los saldos iniciales, o `None` si no se dictó ninguno.

        Las líneas en blanco se descartan antes de armarlo: la pantalla ofrece
        más renglones de los que se usan, y una línea de ceros no es una línea.
        """
        lineas = []
        for pedida in request.opening:
            if pedida.is_empty:
                continue
            if pedida.account_code not in cuentas:
                raise UnknownAccountCode(pedida.account_code)
            lineas.append(
                Line(
                    account_id=cuentas[pedida.account_code],
                    debit=pedida.debit,
                    credit=pedida.credit,
                )
            )

        if not lineas:
            return None

        # Si no cuadra, el constructor lanza y no entra nada: ni las cuentas, ni
        # el mapeo, ni la activación. Es lo correcto —un libro no arranca
        # descuadrado— y es lo que hace que reintentar sea seguro.
        return self._journal.post(
            JournalEntry(
                kind=OPENING,
                entry_date=request.start_date,
                lines=tuple(lineas),
                description=request.description.strip() or OPENING,
            )
        )
