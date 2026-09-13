"""El libro, escrito en la misma sesión de SQLAlchemy (T-1105, RN-59).

Este adaptador es el único sitio del sistema que conoce `account_mappings`. Los
casos de uso le cuentan qué pasó —«se vendió esto», «se cerró la caja con
tanto»— y él traduce a asiento con las funciones puras de `domain/ledger.py` y
escribe las filas.

**No confirma.** Usa la sesión que le pasan y deja el `commit` a quien lo llamó,
que es lo que hace que el asiento y el hecho entren juntos o no entren. Si algo
acá lanza, la venta se revierte con él: un libro no puede tener el estado «venta
sin asiento».

Lo que **no** lanza nunca es un mapeo incompleto, porque no existe: todo papel
sin cuenta cae en 1.9.99 y el asiento balancea igual. Es la pieza que permite
escribir en la transacción de la venta sin violar RNF-4.

**Antes de la fecha de inicio no se escribe nada** (RN-60). Una compañía que
activa contabilidad el 1.º de octubre no asienta la devolución de una venta de
septiembre: esa venta nunca entró al libro, y su devolución sola dejaría un
crédito sin su débito.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.application.ports.clock import Clock
from app.application.ports.ledger import AccountingNotActive
from app.domain.ledger import (
    OPEN,
    AccountMap,
    ClosedSession,
    DrawerMovement,
    JournalEntry,
    Period,
    PurchasedDocument,
    PurchasedLine,
    ReturnDocument,
    SoldDocument,
    SoldLine,
    SupplierPaymentRef,
    assert_open,
    post_cash_close,
    post_cash_movement,
    post_purchase,
    post_return,
    post_sale,
    post_supplier_payment,
)
from app.domain.money import Money
from app.models.model_accounting import Account, AccountingPeriod, AccountMapping
from app.models.model_accounting import JournalEntry as FilaDeAsiento
from app.models.model_accounting import JournalLine as FilaDeLinea
from app.utils.tenancy import compania_actual

#: La cuenta donde cae lo que el mapeo no sabe clasificar (RN-59). El código es
#: el de la plantilla de plan §13.8 y **no** es configurable: es la pieza de la
#: que depende que un asiento automático nunca se quede sin dónde caer, así que
#: `ActivateAccounting` la siembra siempre y RN-64 impide borrarla.
UNCLASSIFIED_CODE = "1.9.99"


class SqlAlchemyLedger:
    """El libro de la compañía de esta petición."""

    def __init__(self, db: Session, *, user_id: int, start_date: date, clock: Clock) -> None:
        self._db = db
        self._user_id = user_id
        self._start_date = start_date
        self._clock = clock
        self._mapeo: AccountMap | None = None

    # ------------------------------------------------------------- el puerto

    def record_sale(self, sale: SoldDocument, lines: Sequence[SoldLine]) -> None:
        self.post(post_sale(sale, lines, self._cuentas()))

    def record_return(self, ret: ReturnDocument, lines: Sequence[SoldLine]) -> None:
        self.post(post_return(ret, lines, self._cuentas()))

    def record_cash_close(
        self, session: ClosedSession, *, expected: Money, counted: Money
    ) -> None:
        self.post(post_cash_close(session, expected, counted, self._cuentas()))

    def record_cash_movement(self, mov: DrawerMovement) -> None:
        self.post(post_cash_movement(mov, self._cuentas()))

    def record_purchase(
        self, entry: PurchasedDocument, lines: Sequence[PurchasedLine]
    ) -> None:
        self.post(post_purchase(entry, lines, self._cuentas()))

    def record_supplier_payment(self, pay: SupplierPaymentRef) -> None:
        self.post(post_supplier_payment(pay, self._cuentas()))

    # ------------------------------------------------------------- escribir

    def post(self, entry: JournalEntry | None) -> int | None:
        """Escribe el asiento y devuelve su id, o `None` si no había qué escribir.

        Es público porque el asiento manual y el de ajuste (T-1109) llegan ya
        armados: los dictó una persona y no salen de ningún evento.
        """
        if entry is None:
            return None
        if entry.entry_date < self._start_date:
            # RN-60: la contabilidad empieza en una fecha y lo anterior no se
            # reconstruye. Devolver `None` y no lanzar es deliberado: una
            # devolución de una venta vieja tiene que poder registrarse.
            return None

        # Todo lo que sigue —el correlativo sin huecos y el periodo que se crea
        # solo— necesita que dos cajas no lo hagan a la vez. Se serializa sobre
        # la fila de la compañía, que existe siempre y es una sola: un
        # correlativo sin huecos **exige** serializar, no hay forma de tenerlo
        # sin eso. El bloqueo dura lo que queda de la transacción, y el asiento
        # es lo último que se escribe antes del `commit`.
        compania = compania_actual()
        self._db.execute(
            text("SELECT id FROM companies WHERE id = :cid FOR UPDATE"), {"cid": compania}
        )

        periodo = self._periodo(entry.entry_date)
        assert_open(Period(periodo.year, periodo.month, periodo.status), entry.entry_date)

        fila = FilaDeAsiento(
            period_id=periodo.id,
            entry_number=self._siguiente_numero(compania),
            entry_date=entry.entry_date,
            kind=entry.kind,
            source_type=entry.source_type,
            source_id=entry.source_id,
            adjusts_entry_id=entry.adjusts_entry_id,
            description=entry.description,
            user_id=self._user_id,
            created_at=self._clock.now(),
        )
        self._db.add(fila)
        # `flush` y no `commit`: asigna el id para las líneas sin cerrar la
        # transacción del hecho que lo originó.
        self._db.flush()

        for linea in entry.lines:
            self._db.add(
                FilaDeLinea(
                    entry_id=fila.id,
                    account_id=linea.account_id,
                    debit=linea.debit.amount,
                    credit=linea.credit.amount,
                    # En porcentaje —13, no 0,13—, que es como lo pide el D-104 y
                    # como lo lee un contador. `as_percent` no sirve acá: escribe
                    # el 10 % como `1E+1`.
                    tax_rate=(
                        None if linea.tax_rate is None else linea.tax_rate.value * 100
                    ),
                    memo=linea.memo,
                )
            )

        return fila.id

    # ------------------------------------------------------------- por dentro

    def _cuentas(self) -> AccountMap:
        """El mapeo vigente, leído una vez por petición (RN-62).

        Una vez y no por asiento: una compra de contado escribe dos —la compra y
        su abono— y los dos tienen que usar las mismas cuentas. Leer dos veces
        abriría la puerta a que alguien guardara el mapeo en medio y la compra
        quedara contra una cuenta y su pago contra otra.
        """
        if self._mapeo is None:
            filas = self._db.query(AccountMapping).all()
            por_clasificar = (
                self._db.query(Account).filter(Account.code == UNCLASSIFIED_CODE).first()
            )
            if por_clasificar is None:
                # Sin 1.9.99 no hay dónde poner lo que falta, y entonces sí se
                # podría detener una venta. Que falte significa que la activación
                # no corrió o que alguien la borró saltándose RN-64.
                raise AccountingNotActive()
            self._mapeo = AccountMap(
                accounts={(fila.event, fila.role): fila.account_id for fila in filas},
                unclassified=por_clasificar.id,
            )
        return self._mapeo

    def _periodo(self, dia: date) -> AccountingPeriod:
        """El mes de esa fecha. Se crea si no existe, y nace abierto.

        Crear el periodo al vuelo es lo que evita un paso administrativo mensual:
        nadie tiene que «abrir octubre» para poder vender el 1.º de octubre.
        """
        fila = (
            self._db.query(AccountingPeriod)
            .filter(AccountingPeriod.year == dia.year, AccountingPeriod.month == dia.month)
            .first()
        )
        if fila is None:
            fila = AccountingPeriod(year=dia.year, month=dia.month, status=OPEN)
            self._db.add(fila)
            self._db.flush()
        return fila

    def _siguiente_numero(self, compania: int) -> int:
        """El correlativo de la compañía, sin huecos (RF-53).

        El `company_id` va escrito a mano: una consulta agregada se salta el
        filtro automático (plan §3.3), y sin él este número sería el máximo de
        **todas** las compañías. La primera compañía no lo notaría y la segunda
        empezaría su libro en el asiento 4 000.
        """
        ultimo = (
            self._db.query(func.max(FilaDeAsiento.entry_number))
            .filter(FilaDeAsiento.company_id == compania)
            .scalar()
        )
        return int(ultimo or 0) + 1
