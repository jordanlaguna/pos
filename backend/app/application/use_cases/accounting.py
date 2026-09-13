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
    JournalRepository,
    MappingRepository,
    PeriodRepository,
)
from app.application.ports.clock import Clock
from app.application.ports.ledger import JournalWriter
from app.application.ports.repositories import UnitOfWork
from app.domain.chart import CHART, TEMPLATES, UNCLASSIFIED_CODE, default_mapping
from app.domain.errors import DomainError, NothingToReclassify
from app.domain.ledger import (
    MANUAL,
    OPENING,
    JournalEntry,
    Line,
    Period,
    check_closeable,
    post_reclassification,
    previous_period,
)
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


class PeriodNotFound(DomainError):
    """Se quiso cerrar un mes que no existe.

    Un mes sin un solo asiento no tiene fila, y cerrarlo no significa nada: lo
    que hay que cerrar es lo que tiene movimiento.
    """

    def __init__(self, year: int, month: int) -> None:
        super().__init__(f"no hay periodo {year}-{month:02d}")
        self.year = year
        self.month = month


@dataclass(frozen=True)
class ManualLine:
    account_id: int
    debit: Money = field(default_factory=Money.zero)
    credit: Money = field(default_factory=Money.zero)
    memo: str | None = None

    @property
    def is_empty(self) -> bool:
        return self.debit.is_zero and self.credit.is_zero


@dataclass(frozen=True)
class ManualEntryRequest:
    entry_date: date
    #: Lo que dice el asiento. **Obligatoria**: es lo único que explica por qué
    #: existe, y sin ella, dentro de un año nadie sabrá qué se corrigió. La
    #: escribe una persona, así que es texto y no código (RN-30).
    description: str
    lines: tuple[ManualLine, ...]
    user_id: int
    #: 'manual' o 'adjustment'. Lo cierra el esquema, que es donde va la forma.
    kind: str = MANUAL
    #: A cuál corrige, si es de ajuste (RN-61).
    adjusts_entry_id: int | None = None


class MissingDescription(DomainError):
    def __init__(self) -> None:
        super().__init__("el asiento manual necesita una descripción")


class RecordManualEntry:
    """Un asiento que alguien dicta (RF-51).

    Es la vía por la que entra todo lo que el POS no sabe: una depreciación, un
    gasto pagado por el dueño, la comisión que el adquirente liquidó. Y la vía
    por la que se corrige lo que quedó mal, con un ajuste que referencia al
    asiento que corrige.

    Lo que este caso de uso comprueba es que las cuentas existan y estén activas;
    que cuadre lo comprueba el constructor del asiento y que el periodo esté
    abierto, el adaptador (RN-58, RN-61). Cada regla en un solo sitio.
    """

    def __init__(
        self,
        *,
        accounts: AccountRepository,
        journal: JournalWriter,
        uow: UnitOfWork,
    ) -> None:
        self._accounts = accounts
        self._journal = journal
        self._uow = uow

    def __call__(self, request: ManualEntryRequest) -> int:
        if not request.description.strip():
            raise MissingDescription()

        activas = {c.id for c in self._accounts.all() if c.is_active}
        lineas = []
        for pedida in request.lines:
            if pedida.is_empty:
                # La pantalla ofrece más renglones de los que se usan.
                continue
            if pedida.account_id not in activas:
                raise AccountNotFound(pedida.account_id)
            lineas.append(
                Line(
                    account_id=pedida.account_id,
                    debit=pedida.debit,
                    credit=pedida.credit,
                    memo=pedida.memo,
                )
            )

        with self._uow:
            id_asiento = self._journal.post(
                JournalEntry(
                    kind=request.kind,
                    entry_date=request.entry_date,
                    lines=tuple(lineas),
                    description=request.description.strip(),
                    adjusts_entry_id=request.adjusts_entry_id,
                )
            )
            self._uow.commit()

        return id_asiento


class ClosePeriod:
    """Cierra un mes, para siempre (RF-52, RN-61).

    No se reabre: reabrir es la puerta por donde un balance ya entregado deja de
    coincidir con el libro. Lo que quedó mal se ajusta en el siguiente, que es lo
    que un contador hace de todos modos.

    `apply()` existe separado del `__call__` por lo mismo que en `PaySupplier`:
    quien cierra también escribe la bitácora, y las dos cosas tienen que entrar
    juntas. Un cierre sin su registro es exactamente lo que RN-61 pide que no
    pase.
    """

    def __init__(
        self, *, periods: PeriodRepository, uow: UnitOfWork, clock: Clock
    ) -> None:
        self._periods = periods
        self._uow = uow
        self._clock = clock

    def __call__(self, *, year: int, month: int, user_id: int):
        with self._uow:
            periodo = self.apply(year=year, month=month, user_id=user_id)
            self._uow.commit()
        return periodo

    def apply(self, *, year: int, month: int, user_id: int):
        """El cierre, comprobado y escrito, **sin confirmar**."""
        periodo = self._periods.get(year, month)
        if periodo is None:
            raise PeriodNotFound(year, month)

        anterior_año, anterior_mes = previous_period(year, month)
        check_closeable(
            Period(periodo.year, periodo.month, periodo.status),
            _como_periodo(self._periods.get(anterior_año, anterior_mes)),
        )

        return self._periods.close(
            periodo, closed_at=self._clock.now(), closed_by=user_id
        )


def _como_periodo(fila) -> Period | None:
    return None if fila is None else Period(fila.year, fila.month, fila.status)


class AccountNotFound(DomainError):
    def __init__(self, account_id: int) -> None:
        super().__init__(f"la cuenta {account_id} no existe")
        self.account_id = account_id


class JournalEntryNotFound(DomainError):
    def __init__(self, entry_id: int) -> None:
        super().__init__(f"el asiento {entry_id} no existe")
        self.entry_id = entry_id


@dataclass(frozen=True)
class ReclassifyRequest:
    entry_id: int
    to_account_id: int
    user_id: int
    #: La frase de quien reclasifica, si escribe una. Sin ella va el código.
    description: str = ""


class Reclassify:
    """Mueve a su cuenta lo que había caído en «por clasificar» (RF-49, RN-59).

    Es la otra mitad de la decisión de plan §13.1: el asiento automático nunca se
    detiene porque lo que falta cae en 1.9.99, y esto es lo que después lo saca de
    ahí. Sin esta pieza, «por clasificar» sería un basurero en vez de una bandeja
    de entrada.

    **No toca el asiento original.** Escribe uno de ajuste que lo referencia, con
    la fecha de hoy: el original pudo quedar en un periodo ya cerrado y entregado,
    y RN-61 dice que eso no se reescribe.
    """

    def __init__(
        self,
        *,
        entries: JournalRepository,
        accounts: AccountRepository,
        journal: JournalWriter,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._entries = entries
        self._accounts = accounts
        self._journal = journal
        self._uow = uow
        self._clock = clock

    def __call__(self, request: ReclassifyRequest) -> int:
        if self._entries.get(request.entry_id) is None:
            raise JournalEntryNotFound(request.entry_id)

        cuentas = self._accounts.all()
        destino = next((c for c in cuentas if c.id == request.to_account_id), None)
        if destino is None or not destino.is_active:
            # Una inactiva se trata como inexistente: no se ofrece para escribir,
            # y mandar un saldo ahí solo cambiaría un problema por otro.
            raise AccountNotFound(request.to_account_id)

        por_clasificar = next(
            (c for c in cuentas if c.code == UNCLASSIFIED_CODE), None
        )
        if por_clasificar is None:
            raise AccountNotFound(request.to_account_id)

        with self._uow:
            ajuste = post_reclassification(
                source_entry_id=request.entry_id,
                lines=self._entries.lines_of(request.entry_id),
                to_account=destino.id,
                unclassified=por_clasificar.id,
                on=self._clock.now().date(),
                description=request.description.strip(),
            )
            if ajuste is None:
                # Pasa de verdad: dos personas mirando la misma pantalla y una
                # reclasifica primero. No es un error del que llega segundo.
                raise NothingToReclassify(request.entry_id)

            id_ajuste = self._journal.post(ajuste)
            self._uow.commit()

        return id_ajuste
