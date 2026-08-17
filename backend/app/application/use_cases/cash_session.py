"""
El turno de caja: abrir, mover efectivo y cerrar.

Lo que hace delicada esta parte no es la aritmética —está en `domain/cash.py` y
es una suma— sino **de dónde salen los números que se suman**. El turno se
delimita por ventana de tiempo sobre las marcas que sella este mismo servidor
(defecto 9), y las ventas con tarjeta no van a la gaveta aunque estén dentro de
la ventana. Ambas cosas viven acá.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.application.ports.clock import Clock
from app.application.ports.repositories import (
    CashRepository,
    ReturnRepository,
    SaleRepository,
    UnitOfWork,
)
from app.domain.cash import CashCount, check_movement, check_opening, difference, expected_amount
from app.domain.errors import DomainError
from app.domain.money import Money

#: El único método de pago que pasa por la gaveta. Tarjeta y transferencia no
#: ponen un colón adentro: sumarlas haría que todo turno con datáfono cerrara
#: con un faltante igual a lo cobrado con tarjeta.
CASH_METHOD = "Efectivo"


class SessionAlreadyOpen(DomainError):
    def __init__(self, user_id: int) -> None:
        super().__init__(f"el cajero {user_id} ya tiene una caja abierta")
        self.user_id = user_id


class NoOpenSession(DomainError):
    def __init__(self, user_id: int) -> None:
        super().__init__(f"el cajero {user_id} no tiene ninguna caja abierta")
        self.user_id = user_id


@dataclass(frozen=True)
class SessionTotals:
    """Las cifras de un turno, ya calculadas."""

    cash_sales: Money
    sales_total: Money
    sales_count: int
    movements_in: Money
    movements_out: Money
    returns_total: Money
    expected: Money
    difference: Money | None
    by_payment_method: list[tuple[str, int, Money]]


class BuildSessionReport:
    """
    Arma las cifras de un turno.

    Las ventas se atribuyen por ventana de tiempo: las del mismo cajero entre la
    apertura y el cierre —o ahora, si sigue abierta—. Por eso `created_at` tiene
    que ser una marca con hora: con solo la fecha, todas las del día caerían en
    el mismo instante y no habría forma de separar dos turnos.
    """

    def __init__(
        self,
        *,
        sales: SaleRepository,
        returns: ReturnRepository,
        cash: CashRepository,
        clock: Clock,
    ) -> None:
        self._sales = sales
        self._returns = returns
        self._cash = cash
        self._clock = clock

    def __call__(
        self,
        *,
        session_id: int,
        user_id: int,
        opening: Money,
        opened_at: datetime,
        closed_at: datetime | None,
        counted: Money | None,
    ) -> SessionTotals:
        fin = closed_at or self._clock.now()

        ventas = self._sales.in_window(user_id, opened_at, fin)
        movimientos = self._cash.movements(session_id)
        devuelto = self._returns.total_in_window(user_id, opened_at, fin)

        por_metodo: dict[str, list] = {}
        for venta in ventas:
            entrada = por_metodo.setdefault(venta.payment_method, [0, Money.zero()])
            entrada[0] += 1
            entrada[1] = entrada[1] + Money(venta.total)

        en_efectivo = Money.sum(
            Money(v.total) for v in ventas if v.payment_method == CASH_METHOD
        )
        entradas = Money.sum(Money(m.amount) for m in movimientos if m.type == "entrada")
        salidas = Money.sum(Money(m.amount) for m in movimientos if m.type == "salida")

        esperado = expected_amount(
            CashCount(
                opening=opening,
                cash_sales=en_efectivo,
                movements_in=entradas,
                movements_out=salidas,
                returns=devuelto,
            )
        )

        return SessionTotals(
            cash_sales=en_efectivo,
            sales_total=Money.sum(Money(v.total) for v in ventas),
            sales_count=len(ventas),
            movements_in=entradas,
            movements_out=salidas,
            returns_total=devuelto,
            expected=esperado,
            difference=difference(counted, esperado) if counted is not None else None,
            by_payment_method=sorted(
                ((m, n, t) for m, (n, t) in por_metodo.items()),
                key=lambda x: x[2],
                reverse=True,
            ),
        )


class OpenCashSession:
    def __init__(self, *, cash: CashRepository, uow: UnitOfWork, clock: Clock) -> None:
        self._cash = cash
        self._uow = uow
        self._clock = clock

    def __call__(self, *, user_id: int, opening: Money, notes: str | None):
        if self._cash.open_session(user_id) is not None:
            raise SessionAlreadyOpen(user_id)
        check_opening(opening)

        with self._uow:
            sesion = self._cash.create_session(
                user_id=user_id,
                opening=opening,
                opened_at=self._clock.now(),
                notes=notes,
            )
            self._uow.commit()
        return sesion


class AddCashMovement:
    """
    Entrada o salida de la gaveta.

    El disponible se calcula **antes** de escribir, con el mismo cálculo del
    arqueo. Sin eso, una salida de más deja el esperado del turno en negativo y
    el corte Z deja de significar nada.
    """

    def __init__(
        self,
        *,
        cash: CashRepository,
        report: BuildSessionReport,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._cash = cash
        self._report = report
        self._uow = uow
        self._clock = clock

    def __call__(self, *, user_id: int, type_: str, amount: Money, reason: str):
        sesion = self._cash.open_session(user_id)
        if sesion is None:
            raise NoOpenSession(user_id)

        cifras = self._report(
            session_id=sesion.id,
            user_id=user_id,
            opening=Money(sesion.opening_amount),
            opened_at=sesion.opened_at,
            closed_at=sesion.closed_at,
            counted=None,
        )
        check_movement(type_, amount, reason, cifras.expected)

        with self._uow:
            movimiento = self._cash.add_movement(
                session_id=sesion.id,
                type_=type_,
                amount=amount,
                reason=reason.strip(),
                created_at=self._clock.now(),
            )
            self._uow.commit()
        return movimiento


class CloseCashSession:
    def __init__(self, *, cash: CashRepository, uow: UnitOfWork, clock: Clock) -> None:
        self._cash = cash
        self._uow = uow
        self._clock = clock

    def __call__(self, *, user_id: int, counted: Money, notes: str | None):
        sesion = self._cash.open_session(user_id)
        if sesion is None:
            raise NoOpenSession(user_id)
        # Cero es un cierre válido —una caja que se vació—; negativo no.
        check_opening(counted)

        with self._uow:
            cerrada = self._cash.close_session(
                sesion.id, counted=counted, closed_at=self._clock.now(), notes=notes
            )
            self._uow.commit()
        return cerrada
