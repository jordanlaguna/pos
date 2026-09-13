"""El libro: de un hecho del negocio a un asiento (F11, RN-58 a RN-63).

Acá no se guarda nada, no se consulta nada y no se mira el reloj. Entran el
hecho —una venta, un cierre de caja, una compra—, sus líneas y el mapeo de
cuentas, y sale un asiento. Es lo que permite comprobar que la venta de 3 × 1 450
deja 7 615,50 por lado sin levantar MySQL.

**Un asiento que no cuadra no es un asiento con un error: no existe** (RN-58).
Por eso la comprobación vive en el constructor de `JournalEntry` y no en una
función aparte que alguien pueda olvidar llamar. No hay forma de tener en las
manos un asiento desbalanceado.

**Y nunca falta** (RN-59). El asiento se escribe en la misma transacción de la
venta, así que un mapeo incompleto detendría al cajero, y eso viola RNF-4. La
salida no es un `try` alrededor: es que el mapeo **no pueda** estar incompleto.
Todo papel sin cuenta asignada cae en «por clasificar» —1.9.99, de sistema, que
existe desde la activación—. El asiento siempre balancea y siempre existe; lo
que falta se ve en rojo en la pantalla del contador, no en la caja.

Tres cosas que este módulo decide y conviene leer antes de cambiarlo:

* **Las cifras salen de las líneas, no del encabezado.** El débito de una venta
  es la suma de las bases y los impuestos de sus líneas, no `sales.total`. Los
  dos valen lo mismo por construcción (RN-10), y derivarlo de las líneas es lo
  que hace imposible que un encabezado que se desvió un céntimo produzca un
  asiento que no cuadra —y con él, una venta que no se puede cobrar—.

* **La descripción es un código, no una frase.** El backend no escribe texto
  para personas (RN-30): un asiento automático lleva el código del evento y el
  POS arma «Venta n.º 412» con `source_type` y `source_id`. La frase de un
  asiento manual sí es texto, pero ese lo escribió quien lo dictó, igual que el
  motivo de un movimiento de caja.

* **Todo `post_*` puede devolver `None`.** Un turno que cuadra no deja asiento,
  una salida de caja que ya asentó su abono tampoco, y una venta de cero colones
  no tiene nada que decir. Devolver `None` es más honesto que un asiento de
  ceros, que además no se podría construir: una línea vacía no es una línea.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from .errors import EntryNotBalanced, InvalidEntryLine, PeriodClosed
from .money import Money
from .sale import CASH_METHOD
from .tax import TaxRate

# --------------------------------------------------------------- vocabulario
#
# Constantes y no enums, por lo mismo que `MOVEMENT_TYPES` y `PAYMENT_METHODS`:
# en la base son `VARCHAR`, y obligar a la capa de persistencia a conocer un enum
# de Python no compra nada.

#: Los seis tipos de cuenta. De esto salen el estado de resultados y el balance:
#: qué suma dónde.
ACCOUNT_KINDS: tuple[str, ...] = (
    "asset",
    "liability",
    "equity",
    "income",
    "cost",
    "expense",
)

#: Los tipos cuyo saldo natural **crece con el débito**. Los otros tres crecen
#: con el crédito. Es la única regla de signos que hay en contabilidad y la usan
#: los tres reportes de saldos.
DEBIT_KINDS: frozenset[str] = frozenset({"asset", "cost", "expense"})

#: Cómo nació el asiento. 'auto' lo escribió un evento; 'manual' lo dictó
#: alguien; 'adjustment' corrige a otro (RN-61); 'opening' son los saldos
#: iniciales del día en que arrancó la contabilidad (RN-60).
ENTRY_KINDS: tuple[str, ...] = ("auto", "manual", "adjustment", "opening")

AUTO = "auto"
MANUAL = "manual"
ADJUSTMENT = "adjustment"
OPENING = "opening"

# Los eventos del negocio que dejan asiento.
SALE = "sale"
RETURN = "return"
CASH_CLOSE = "cash_close"
CASH_MOVEMENT = "cash_movement"
PURCHASE = "purchase"
SUPPLIER_PAYMENT = "supplier_payment"
PAYROLL = "payroll"

EVENTS: tuple[str, ...] = (
    SALE,
    RETURN,
    CASH_CLOSE,
    CASH_MOVEMENT,
    PURCHASE,
    SUPPLIER_PAYMENT,
    PAYROLL,
)

# De qué tabla salió el asiento. **No son los mismos nombres que los eventos** y
# no pueden serlo: el evento 'cash_close' nace de una fila de `cash_sessions`, y
# el evento 'purchase' de una de `stock_entries`, porque una compra es una
# entrada de mercadería con tres datos más (RN-52).
SOURCE_SALE = "sale"
SOURCE_RETURN = "return"
SOURCE_CASH_SESSION = "cash_session"
SOURCE_CASH_MOVEMENT = "cash_movement"
SOURCE_STOCK_ENTRY = "stock_entry"
SOURCE_SUPPLIER_PAYMENT = "supplier_payment"
SOURCE_PAYROLL_RUN = "payroll_run"

# Los papeles que una cuenta puede jugar dentro de un evento.
CASH = "cash"
BANK = "bank"
CARDS_RECEIVABLE = "cards_receivable"
RECEIVABLE = "receivable"
VAT_PAYABLE = "vat_payable"
VAT_CREDIT = "vat_credit"
INVENTORY = "inventory"
COGS = "cogs"
PAYABLES = "payables"
CASH_OVER = "cash_over"
CASH_SHORT = "cash_short"
SALES_RETURNS = "sales_returns"

#: Prefijo de los papeles de venta por tarifa: 'sales_13', 'sales_1', 'sales_0'.
SALES = "sales"

#: El código de descripción de un ajuste que mueve un saldo de «por clasificar»
#: a su cuenta. Como el resto de las descripciones automáticas, es un código y no
#: una frase: el POS arma la oración (RN-30).
RECLASSIFY = "reclassify"

#: La contrapartida de un movimiento de gaveta. **Queda sin mapear a propósito**
#: y por eso cae en 1.9.99: el sistema sabe que entraron ₡5 000, no de dónde
#: salieron. Quien lo sabe es quien los metió, y lo dice reclasificando.
COUNTERPART = "counterpart"

#: El papel que nunca se mapea. Se usa cuando el evento trae un dato que no
#: corresponde a ninguno de los de arriba —un método de pago desconocido— para
#: que la línea caiga en «por clasificar» con un motivo legible en el `memo`.
UNCLASSIFIED = "unclassified"

#: A qué papel va el cobro de una venta, según su método de pago.
#:
#: Los valores son los cuatro de `PAYMENT_METHODS`, el conjunto cerrado que
#: define `domain/sale.py` (T-1104). Que estén los cuatro lo comprueba una
#: prueba: si alguien agrega un método y olvida su papel, todas las ventas
#: cobradas con él se irían a «por clasificar» sin que nada avisara.
#:
#: Un método que no esté acá —una venta anterior a T-1104, una fila escrita a
#: mano— no detiene nada: cae en «por clasificar», que es justo para lo que está.
METHOD_ROLES: dict[str, str] = {
    CASH_METHOD: CASH,
    "Tarjeta de crédito": CARDS_RECEIVABLE,
    # SINPE Móvil y la transferencia entran igual: al banco. No son la gaveta, y
    # por eso el arqueo tampoco las cuenta (`expected_amount`).
    "Transferencia bancaria": BANK,
    "Pago móvil": BANK,
}

#: Con qué se le pagó al proveedor (RN-56). 'other' —un cheque, una compensación—
#: queda sin papel y cae en «por clasificar»: el sistema no sabe de dónde salió
#: esa plata.
SUPPLIER_PAYMENT_ROLES: dict[str, str] = {"cash": CASH, "transfer": BANK}

OPEN = "open"
CLOSED = "closed"


def _percent_text(rate: TaxRate) -> str:
    """'13', '1', '0', '0.5'. El nombre del papel de venta de esa tarifa.

    No usa `TaxRate.as_percent` porque `Decimal.normalize()` escribe los
    múltiplos de diez en notación científica —el 10 % sale como `1E+1`— y el
    papel quedaría en 'sales_1E+1', que no está en ningún mapeo y mandaría todas
    las ventas al 10 % a «por clasificar» sin que nada avise.
    """
    entero, _, decimales = format(rate.value * 100, "f").partition(".")
    decimales = decimales.rstrip("0")
    return f"{entero}.{decimales}" if decimales else entero


def sales_role(rate: TaxRate) -> str:
    """El papel de la venta a esa tarifa: 'sales_13'.

    Que el papel lleve la tarifa adentro es lo que permite que el catálogo tenga
    una cuenta de ingresos por tarifa —4.1.01 a 4.1.05— sin que este módulo
    conozca ninguna de las cinco. Una tarifa nueva del catálogo de Hacienda cae
    en «por clasificar» hasta que el contador le asigne cuenta, y mientras tanto
    se vende igual.
    """
    return f"{SALES}_{_percent_text(rate)}"


@dataclass(frozen=True)
class AccountMap:
    """Qué cuenta usa cada papel de cada evento, y dónde cae lo que no tiene.

    `unclassified` es la cuenta 1.9.99, de sistema. No es un valor por omisión
    cómodo: es la pieza que sostiene RN-59. Sin ella, un mapeo al que le falta
    una fila detendría una venta.
    """

    #: `(evento, papel) → id de cuenta`. Es el contenido de `account_mappings`
    #: **vigente al momento del evento** (RN-62): quien lo arma lo lee una vez y
    #: el asiento guarda los ids, así que cambiar el mapeo mañana no reescribe lo
    #: que ya está en el libro.
    accounts: Mapping[tuple[str, str], int]
    unclassified: int

    def account_for(self, event: str, role: str) -> int:
        return self.accounts.get((event, role), self.unclassified)

    def is_mapped(self, event: str, role: str) -> bool:
        """Si el papel tiene cuenta propia. Lo usa la pantalla del mapeo para
        pintar en rojo lo que falta, antes de que caiga en 1.9.99."""
        return (event, role) in self.accounts


@dataclass(frozen=True)
class Line:
    """Una línea del asiento.

    Débito y crédito en dos columnas y no un monto con signo: es como se lee un
    libro y como se cuadra a ojo. Que una de las dos sea cero se vigila acá —y no
    con un CHECK en la base— para que la regla se escriba una vez, con su prueba,
    y valga igual para el asiento automático y para el que alguien teclea.
    """

    account_id: int
    debit: Money = Money.zero()
    credit: Money = Money.zero()
    #: Solo en las líneas de IVA. Es lo que deja el débito y el crédito fiscal
    #: por tarifa a la vista dentro del propio libro (RN-65).
    tax_rate: TaxRate | None = None
    #: El papel que originó la línea, **en código** y no en frase (RN-30). Es lo
    #: que permite que la pantalla de «por clasificar» diga qué falta mapear y no
    #: solo cuánto.
    memo: str | None = None

    def __post_init__(self) -> None:
        if self.debit.is_negative or self.credit.is_negative:
            raise InvalidEntryLine("negative")
        if self.debit.is_positive and self.credit.is_positive:
            raise InvalidEntryLine("both_sides")
        if self.debit.is_zero and self.credit.is_zero:
            raise InvalidEntryLine("empty")

    @classmethod
    def debit_of(
        cls,
        account_id: int,
        amount: Money,
        *,
        tax_rate: TaxRate | None = None,
        memo: str | None = None,
    ) -> Line:
        return cls(account_id=account_id, debit=amount, tax_rate=tax_rate, memo=memo)

    @classmethod
    def credit_of(
        cls,
        account_id: int,
        amount: Money,
        *,
        tax_rate: TaxRate | None = None,
        memo: str | None = None,
    ) -> Line:
        return cls(account_id=account_id, credit=amount, tax_rate=tax_rate, memo=memo)


@dataclass(frozen=True)
class JournalEntry:
    """Un asiento, que por existir ya balancea (RN-58)."""

    kind: str
    entry_date: date
    lines: tuple[Line, ...]
    #: El código del evento en los automáticos; la frase de quien lo dictó en los
    #: manuales. Ver la nota del encabezado del módulo.
    description: str = ""
    source_type: str | None = None
    source_id: int | None = None
    #: A cuál corrige, si es de ajuste (RN-61).
    adjusts_entry_id: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "lines", tuple(self.lines))
        if not self.lines:
            raise InvalidEntryLine("no_lines")
        if self.debits != self.credits:
            raise EntryNotBalanced(str(self.debits), str(self.credits))

    @property
    def debits(self) -> Money:
        return Money.sum(linea.debit for linea in self.lines)

    @property
    def credits(self) -> Money:
        return Money.sum(linea.credit for linea in self.lines)

    @property
    def total(self) -> Money:
        """Lo que mueve el asiento. Un solo número porque los dos lados son
        iguales: eso es lo que significa que exista."""
        return self.debits


# ------------------------------------------------------------------- eventos


@dataclass(frozen=True)
class SoldDocument:
    """La cabecera de una venta, con lo único que el libro necesita de ella."""

    id: int
    date: date
    payment_method: str


@dataclass(frozen=True)
class SoldLine:
    """Una línea vendida o devuelta, como quedó guardada.

    `unit_cost` es el costo **congelado al vender** (RN-63), no el que tenga el
    producto hoy. En `None` cuando no se sabe —una venta anterior a F11, un
    producto que nunca se compró— y entonces la línea no asienta costo ni
    inventario: inventar un cero diría que la mercadería fue gratis y la utilidad
    del mes saldría inflada.
    """

    subtotal: Money
    tax: Money
    tax_rate: TaxRate
    quantity: int
    unit_cost: Money | None = None

    @property
    def cost(self) -> Money:
        if self.unit_cost is None:
            return Money.zero()
        return self.unit_cost * self.quantity


@dataclass(frozen=True)
class ReturnDocument:
    id: int
    date: date


@dataclass(frozen=True)
class ClosedSession:
    """Un turno que se cierra."""

    id: int
    date: date


@dataclass(frozen=True)
class DrawerMovement:
    """Una entrada o una salida de la gaveta."""

    id: int
    date: date
    #: 'entrada' | 'salida', los mismos de `domain/cash.py`.
    type: str
    amount: Money
    #: Si nació de un abono a proveedor (RN-56). Entonces **no deja asiento**: el
    #: abono ya asienta esa misma plata, y las dos juntas la contarían dos veces.
    from_supplier_payment: bool = False


@dataclass(frozen=True)
class PurchasedDocument:
    """La cabecera de una compra, que es una entrada de mercadería (RN-52)."""

    id: int
    date: date


@dataclass(frozen=True)
class PurchasedLine:
    """Una línea del documento del proveedor, con **su** impuesto (RN-53)."""

    subtotal: Money
    tax: Money
    tax_rate: TaxRate


@dataclass(frozen=True)
class SupplierPaymentRef:
    id: int
    date: date
    amount: Money
    #: 'cash' | 'transfer' | 'other', los de `domain/purchases.py`.
    method: str


def _by_rate(
    lines: Sequence[SoldLine] | Sequence[PurchasedLine],
) -> tuple[tuple[TaxRate, Money, Money], ...]:
    """`(tarifa, base, impuesto)` por tarifa, de menor a mayor.

    Ordenado para que el asiento salga siempre igual: sin esto, el orden de las
    líneas lo decidiría en qué fila del documento apareció cada tarifa.
    """
    acumulado: dict[TaxRate, tuple[Money, Money]] = {}
    for linea in lines:
        base, impuesto = acumulado.get(linea.tax_rate, (Money.zero(), Money.zero()))
        acumulado[linea.tax_rate] = (base + linea.subtotal, impuesto + linea.tax)
    return tuple((tarifa, base, impuesto) for tarifa, (base, impuesto) in sorted(acumulado.items()))


def _entry(
    kind: str,
    on: date,
    description: str,
    lines: list[Line],
    *,
    source_type: str | None = None,
    source_id: int | None = None,
    adjusts_entry_id: int | None = None,
) -> JournalEntry | None:
    """El asiento, o `None` si no quedó ninguna línea que escribir."""
    if not lines:
        return None
    return JournalEntry(
        kind=kind,
        entry_date=on,
        lines=tuple(lines),
        description=description,
        source_type=source_type,
        source_id=source_id,
        adjusts_entry_id=adjusts_entry_id,
    )


def post_sale(
    sale: SoldDocument, lines: Sequence[SoldLine], mapping: AccountMap
) -> JournalEntry | None:
    """La venta.

        subtotal 4 350,00 · IVA 565,50 · total 4 915,50, costo unitario 900

        D  Caja                        4 915,50
           C  Ventas 13 %                          4 350,00
           C  IVA por pagar 13 %                     565,50   (tax_rate 13)
        D  Costo de ventas             2 700,00
           C  Inventario                           2 700,00

    El cobro va a una cuenta u otra según el método de pago, y **la tarjeta va
    por su bruto** a «tarjetas por cobrar»: la comisión y la retención del
    adquirente se asientan cuando el banco liquida, que es cuando se saben.
    Estimarlas acá sería asentar un número que después no coincide con el banco,
    y conciliar dos números que nunca fueron iguales es peor que asentar tarde.

    Una tarifa sin base —una línea regalada— no deja línea de ingreso: una línea
    de cero no es una línea. Si la venta entera fue de cero y ningún producto
    tenía costo, no queda nada que asentar y devuelve `None`.
    """
    por_tarifa = _by_rate(lines)

    ingresos: list[Line] = []
    cobro = Money.zero()
    for tarifa, base, impuesto in por_tarifa:
        if base.is_positive:
            papel = sales_role(tarifa)
            ingresos.append(
                Line.credit_of(mapping.account_for(SALE, papel), base, memo=papel)
            )
        if impuesto.is_positive:
            ingresos.append(
                Line.credit_of(
                    mapping.account_for(SALE, VAT_PAYABLE),
                    impuesto,
                    tax_rate=tarifa,
                    memo=VAT_PAYABLE,
                )
            )
        cobro = cobro + base + impuesto

    asiento: list[Line] = []
    if cobro.is_positive:
        papel = METHOD_ROLES.get(sale.payment_method, UNCLASSIFIED)
        asiento.append(Line.debit_of(mapping.account_for(SALE, papel), cobro, memo=papel))
    asiento.extend(ingresos)

    costo = Money.sum(linea.cost for linea in lines)
    if costo.is_positive:
        asiento.append(Line.debit_of(mapping.account_for(SALE, COGS), costo, memo=COGS))
        asiento.append(
            Line.credit_of(mapping.account_for(SALE, INVENTORY), costo, memo=INVENTORY)
        )

    return _entry(AUTO, sale.date, SALE, asiento, source_type=SOURCE_SALE, source_id=sale.id)


def post_return(
    ret: ReturnDocument, lines: Sequence[SoldLine], mapping: AccountMap
) -> JournalEntry | None:
    """La devolución: la venta al revés, con **la tarifa de su venta** (RN-12).

        D  Devoluciones sobre ventas
        D  IVA por pagar                          (tax_rate de cada línea)
           C  Caja
        D  Inventario
           C  Costo de ventas

    El reembolso sale de la gaveta y no de la cuenta por la que entró la venta,
    porque es lo que de verdad pasa y lo que ya cuenta el arqueo:
    `expected_amount` resta **todas** las devoluciones del efectivo esperado. Si
    el libro dijera otra cosa, el turno y el asiento dejarían de coincidir.

    La base vuelve a una cuenta propia —«Devoluciones sobre ventas»— y no se
    resta de la de ingresos: un contador quiere ver cuánto se vendió y cuánto se
    devolvió, no la diferencia.
    """
    por_tarifa = _by_rate(lines)

    asiento: list[Line] = []
    devuelto = Money.sum(linea.subtotal for linea in lines)
    if devuelto.is_positive:
        asiento.append(
            Line.debit_of(
                mapping.account_for(RETURN, SALES_RETURNS), devuelto, memo=SALES_RETURNS
            )
        )

    reembolso = Money.zero()
    for tarifa, base, impuesto in por_tarifa:
        if impuesto.is_positive:
            asiento.append(
                Line.debit_of(
                    mapping.account_for(RETURN, VAT_PAYABLE),
                    impuesto,
                    tax_rate=tarifa,
                    memo=VAT_PAYABLE,
                )
            )
        reembolso = reembolso + base + impuesto

    if reembolso.is_positive:
        asiento.append(
            Line.credit_of(mapping.account_for(RETURN, CASH), reembolso, memo=CASH)
        )

    costo = Money.sum(linea.cost for linea in lines)
    if costo.is_positive:
        asiento.append(
            Line.debit_of(mapping.account_for(RETURN, INVENTORY), costo, memo=INVENTORY)
        )
        asiento.append(Line.credit_of(mapping.account_for(RETURN, COGS), costo, memo=COGS))

    return _entry(
        AUTO, ret.date, RETURN, asiento, source_type=SOURCE_RETURN, source_id=ret.id
    )


def post_cash_close(
    session: ClosedSession, expected: Money, counted: Money, mapping: AccountMap
) -> JournalEntry | None:
    """El cierre de caja, **solo si no cuadró**.

    Un turno cuadrado no deja asiento: no pasó nada que anotar. La plata que
    entró y salió ya la asentaron la venta y el movimiento.

        esperado 53 277,00 · contado 53 000,00  →  faltante 277,00

        D  Faltantes de caja              277,00
           C  Caja                                  277,00
    """
    diferencia = counted - expected
    if diferencia.is_zero:
        return None

    if diferencia.is_positive:
        lineas = [
            Line.debit_of(mapping.account_for(CASH_CLOSE, CASH), diferencia, memo=CASH),
            Line.credit_of(
                mapping.account_for(CASH_CLOSE, CASH_OVER), diferencia, memo=CASH_OVER
            ),
        ]
    else:
        faltante = abs(diferencia)
        lineas = [
            Line.debit_of(
                mapping.account_for(CASH_CLOSE, CASH_SHORT), faltante, memo=CASH_SHORT
            ),
            Line.credit_of(mapping.account_for(CASH_CLOSE, CASH), faltante, memo=CASH),
        ]

    return _entry(
        AUTO,
        session.date,
        CASH_CLOSE,
        lineas,
        source_type=SOURCE_CASH_SESSION,
        source_id=session.id,
    )


def post_cash_movement(mov: DrawerMovement, mapping: AccountMap) -> JournalEntry | None:
    """Una entrada o una salida de la gaveta, contra «por clasificar».

    La contrapartida queda sin mapear a propósito: el sistema sabe que entraron
    ₡5 000, no de dónde salieron. Quien lo sabe es quien los metió, y lo dice
    reclasificando.

    **La salida que nació de un abono a proveedor no deja asiento.** Esa plata ya
    la asentó el abono —proveedores contra caja—, y las dos juntas la contarían
    dos veces: la caja quedaría con el doble de salidas y el pasivo sin rebajar.
    """
    if mov.from_supplier_payment:
        return None
    if not mov.amount.is_positive:
        return None

    caja = mapping.account_for(CASH_MOVEMENT, CASH)
    contra = mapping.account_for(CASH_MOVEMENT, COUNTERPART)
    if mov.type == "entrada":
        lineas = [
            Line.debit_of(caja, mov.amount, memo=CASH),
            Line.credit_of(contra, mov.amount, memo=COUNTERPART),
        ]
    else:
        lineas = [
            Line.debit_of(contra, mov.amount, memo=COUNTERPART),
            Line.credit_of(caja, mov.amount, memo=CASH),
        ]

    return _entry(
        AUTO,
        mov.date,
        CASH_MOVEMENT,
        lineas,
        source_type=SOURCE_CASH_MOVEMENT,
        source_id=mov.id,
    )


def post_purchase(
    entry: PurchasedDocument, lines: Sequence[PurchasedLine], mapping: AccountMap
) -> JournalEntry | None:
    """La compra.

        D  Inventario                 100 000,00
        D  IVA crédito fiscal          13 000,00   (tax_rate 13)
           C  Proveedores                          113 000,00

    **Siempre contra proveedores, también la de contado.** El plan decía «caja
    (contado)», y eso contaría la plata dos veces: desde F10 una compra de
    contado con método de pago crea su propio abono, y el abono asienta
    proveedores contra caja. Cargando siempre el pasivo, la de contado queda —
    sumando las dos— en inventario e IVA contra caja, que es lo correcto; y la de
    contado **sin** método de pago queda debiendo, que también es lo correcto,
    porque nadie registró que se pagara.
    """
    por_tarifa = _by_rate(lines)

    inventario = Money.sum(linea.subtotal for linea in lines)
    asiento: list[Line] = []
    if inventario.is_positive:
        asiento.append(
            Line.debit_of(mapping.account_for(PURCHASE, INVENTORY), inventario, memo=INVENTORY)
        )

    deuda = inventario
    for tarifa, _base, impuesto in por_tarifa:
        if impuesto.is_positive:
            asiento.append(
                Line.debit_of(
                    mapping.account_for(PURCHASE, VAT_CREDIT),
                    impuesto,
                    tax_rate=tarifa,
                    memo=VAT_CREDIT,
                )
            )
            deuda = deuda + impuesto

    if deuda.is_positive:
        asiento.append(
            Line.credit_of(mapping.account_for(PURCHASE, PAYABLES), deuda, memo=PAYABLES)
        )

    return _entry(
        AUTO,
        entry.date,
        PURCHASE,
        asiento,
        source_type=SOURCE_STOCK_ENTRY,
        source_id=entry.id,
    )


def post_supplier_payment(
    pay: SupplierPaymentRef, mapping: AccountMap
) -> JournalEntry | None:
    """El abono al proveedor: el pasivo contra de dónde salió la plata.

        D  Proveedores                 50 000,00
           C  Caja                                 50 000,00

    Un abono por «otro» medio —un cheque, una compensación— no dice de dónde
    salió, así que el crédito cae en «por clasificar». Es preferible a suponer
    banco: el saldo bancario del libro dejaría de coincidir con el del banco, y
    eso se descubre semanas después conciliando.
    """
    if not pay.amount.is_positive:
        return None

    papel = SUPPLIER_PAYMENT_ROLES.get(pay.method, UNCLASSIFIED)
    lineas = [
        Line.debit_of(
            mapping.account_for(SUPPLIER_PAYMENT, PAYABLES), pay.amount, memo=PAYABLES
        ),
        Line.credit_of(mapping.account_for(SUPPLIER_PAYMENT, papel), pay.amount, memo=papel),
    ]

    return _entry(
        AUTO,
        pay.date,
        SUPPLIER_PAYMENT,
        lineas,
        source_type=SOURCE_SUPPLIER_PAYMENT,
        source_id=pay.id,
    )


def post_reclassification(
    *,
    source_entry_id: int,
    lines: Sequence[Line],
    to_account: int,
    unclassified: int,
    on: date,
    description: str = "",
) -> JournalEntry | None:
    """Saca de «por clasificar» lo que cayó ahí y lo pone donde va (RN-59).

        antes:  D  Por clasificar   5 000,00
        ajuste: D  Gastos generales 5 000,00
                   C  Por clasificar            5 000,00

    Es un asiento de **ajuste**, con `adjusts_entry_id` apuntando al original, y
    **con la fecha de hoy y no la del original**. Las dos cosas son RN-61: el
    asiento que quedó mal no se toca —pudo quedar en un periodo ya cerrado y
    entregado— y lo que se corrige se corrige en el periodo abierto.

    Cada línea se invierte del lado en que estaba, así que el saldo de 1.9.99
    para ese asiento queda exactamente en cero. Eso es lo que hace que la
    pantalla del contador pueda decir «no queda nada por clasificar» mirando un
    saldo y no llevando una lista aparte de lo ya resuelto.
    """
    movimientos: list[Line] = []
    for linea in lines:
        if linea.account_id != unclassified:
            continue
        if linea.debit.is_positive:
            movimientos.append(Line.debit_of(to_account, linea.debit, memo=linea.memo))
            movimientos.append(Line.credit_of(unclassified, linea.debit, memo=linea.memo))
        else:
            movimientos.append(Line.debit_of(unclassified, linea.credit, memo=linea.memo))
            movimientos.append(Line.credit_of(to_account, linea.credit, memo=linea.memo))

    return _entry(
        ADJUSTMENT,
        on,
        description or RECLASSIFY,
        movimientos,
        adjusts_entry_id=source_entry_id,
    )


# ------------------------------------------------------------------ periodos


@dataclass(frozen=True)
class Period:
    """Un mes contable."""

    year: int
    month: int
    status: str = OPEN

    @property
    def is_closed(self) -> bool:
        return self.status == CLOSED


def assert_open(period: Period | None, on: date) -> None:
    """RN-61: nada se escribe con fecha dentro de un periodo cerrado.

    `None` es el mes que todavía no existe, y un mes que no existe nace abierto:
    la primera venta de octubre crea el periodo de octubre. Lo que no puede pasar
    es que nazca **anterior** a uno cerrado, y de eso se encarga quien cierra, no
    quien escribe: cerrar exige que el anterior esté cerrado (RF-52).
    """
    if period is not None and period.is_closed:
        raise PeriodClosed(on.year, on.month)
