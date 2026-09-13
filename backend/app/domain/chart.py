"""La plantilla de cuentas y el mapeo por omisión (T-1107, plan §13.8).

Es **una plantilla de trabajo, no una norma**. El contador de cada compañía la
ajusta desde la primera semana: agrega sus cuentas de gasto, parte el inventario
en bodegas, renombra lo que su despacho llama de otra manera. Lo único que no
puede tocar son las cuentas de sistema, porque el mapeo las necesita (RN-64).

Los nombres están en español y son **datos, no mensajes**: el catálogo de cuentas
es un documento de la compañía, lo imprime su contador y lo edita a mano, así que
no pasa por los catálogos de traducción del POS. Lo que sí sigue sin escribirse
acá es cualquier «no» del servidor, que viaja en código (RN-30).

**El mapeo tiene que estar completo.** Un papel sin fila no rompe nada —cae en
1.9.99, que para eso está— pero sí deja al contador un saldo en rojo el primer
día, por algo que el sistema sabía desde antes de empezar. Una prueba recorre los
papeles que los `post_*` pueden pedir y exige que todos tengan cuenta, salvo los
que se dejan sueltos a propósito y están escritos abajo con su porqué.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import AccountInUse, AccountIsSystem
from .ledger import (
    BANK,
    CARDS_RECEIVABLE,
    CASH,
    CASH_CLOSE,
    CASH_MOVEMENT,
    CASH_OVER,
    CASH_SHORT,
    COGS,
    COUNTERPART,
    INVENTORY,
    PAYABLES,
    PAYROLL,
    PURCHASE,
    RECEIVABLE,
    RETURN,
    SALE,
    SALES_RETURNS,
    SUPPLIER_PAYMENT,
    UNCLASSIFIED,
    VAT_CREDIT,
    VAT_PAYABLE,
    sales_role,
)
from .tax import TaxRate

#: La única plantilla que hay hoy. Se pide por nombre para que agregar la de un
#: taller o la de un restaurante no cambie ninguna firma.
COMMERCE = "commerce"
TEMPLATES: tuple[str, ...] = (COMMERCE,)

#: La cuenta donde cae lo que el mapeo no sabe clasificar (RN-59). **No es
#: configurable**: es la pieza de la que depende que un asiento automático nunca
#: se quede sin dónde caer, así que la activación la siembra siempre y RN-64
#: impide borrarla.
UNCLASSIFIED_CODE = "1.9.99"


@dataclass(frozen=True)
class AccountTemplate:
    code: str
    name: str
    kind: str
    #: De sistema: la usa el mapeo, así que no se borra ni se desactiva (RN-64).
    is_system: bool = True


#: Las tarifas que tienen cuenta propia de ingresos, con el código que les toca.
#: Son las del catálogo de Hacienda que se cobran hoy en el país. Una tarifa
#: nueva no rompe nada: cae en «por clasificar» hasta que el contador le asigne
#: cuenta, y mientras tanto se sigue vendiendo.
SALES_ACCOUNTS: tuple[tuple[str, TaxRate], ...] = (
    ("4.1.01", TaxRate.percent(13)),
    ("4.1.02", TaxRate.percent(4)),
    ("4.1.03", TaxRate.percent(2)),
    ("4.1.04", TaxRate.percent(1)),
    ("4.1.05", TaxRate.zero()),
)

CHART: tuple[AccountTemplate, ...] = (
    # ------------------------------------------------------------- activo
    AccountTemplate("1.1.01", "Caja", "asset"),
    AccountTemplate("1.1.02", "Bancos", "asset"),
    AccountTemplate("1.1.03", "Tarjetas por cobrar", "asset"),
    AccountTemplate("1.1.04", "Clientes", "asset"),
    AccountTemplate("1.1.05", "IVA crédito fiscal", "asset"),
    AccountTemplate("1.1.06", "Retenciones a favor", "asset", is_system=False),
    AccountTemplate("1.2.01", "Inventario", "asset"),
    # La que sostiene RN-59. Sin ella un mapeo incompleto detendría una venta.
    AccountTemplate("1.9.99", "Por clasificar", "asset"),
    # ------------------------------------------------------------- pasivo
    AccountTemplate("2.1.01", "Proveedores", "liability"),
    AccountTemplate("2.1.02", "IVA por pagar", "liability"),
    AccountTemplate("2.1.03", "Retenciones de renta por pagar", "liability"),
    AccountTemplate("2.1.04", "CCSS por pagar", "liability"),
    AccountTemplate("2.1.05", "Salarios por pagar", "liability"),
    AccountTemplate("2.1.06", "Otras deducciones por pagar", "liability"),
    # --------------------------------------------------------- patrimonio
    AccountTemplate("3.1.01", "Capital", "equity"),
    AccountTemplate("3.2.01", "Resultados acumulados", "equity"),
    # ----------------------------------------------------------- ingresos
    AccountTemplate("4.1.01", "Ventas 13 %", "income"),
    AccountTemplate("4.1.02", "Ventas 4 %", "income"),
    AccountTemplate("4.1.03", "Ventas 2 %", "income"),
    AccountTemplate("4.1.04", "Ventas 1 %", "income"),
    AccountTemplate("4.1.05", "Ventas exentas", "income"),
    AccountTemplate("4.2.01", "Devoluciones sobre ventas", "income"),
    AccountTemplate("4.9.01", "Sobrantes de caja", "income"),
    # -------------------------------------------------------------- costo
    AccountTemplate("5.1.01", "Costo de ventas", "cost"),
    # ------------------------------------------------------------- gastos
    AccountTemplate("6.1.01", "Salarios", "expense"),
    AccountTemplate("6.1.02", "Cargas sociales patronales", "expense"),
    AccountTemplate("6.1.03", "Aguinaldo", "expense"),
    AccountTemplate("6.2.01", "Comisiones de tarjetas", "expense", is_system=False),
    AccountTemplate("6.9.01", "Faltantes de caja", "expense"),
    AccountTemplate("6.9.02", "Gastos generales", "expense", is_system=False),
)

# Los papeles de planilla (F12). Las cuentas ya están en la plantilla porque el
# plan las siembra desde acá; los nombres de los papeles los confirma F12.
SALARIES = "salaries"
EMPLOYER_CONTRIBUTIONS = "employer_contributions"
INCOME_TAX_PAYABLE = "income_tax_payable"
SOCIAL_SECURITY_PAYABLE = "social_security_payable"
SALARIES_PAYABLE = "salaries_payable"
OTHER_DEDUCTIONS_PAYABLE = "other_deductions_payable"


def default_mapping() -> dict[tuple[str, str], str]:
    """`(evento, papel) → código de cuenta`, el mapeo con el que se arranca."""
    mapeo: dict[tuple[str, str], str] = {
        # -------------------------------------------------------- la venta
        (SALE, CASH): "1.1.01",
        (SALE, CARDS_RECEIVABLE): "1.1.03",
        # La transferencia y SINPE Móvil entran al banco. No estaba en el plan
        # y sin esta fila toda venta cobrada así caía en «por clasificar»
        # (T-1107, 2026-09-12).
        (SALE, BANK): "1.1.02",
        # La venta a crédito todavía no existe —no hay método de pago que lleve
        # acá—, y la fila se siembra igual: el día que exista, el asiento ya
        # sabe dónde va.
        (SALE, RECEIVABLE): "1.1.04",
        (SALE, VAT_PAYABLE): "2.1.02",
        (SALE, COGS): "5.1.01",
        (SALE, INVENTORY): "1.2.01",
        # --------------------------------------------------- la devolución
        (RETURN, SALES_RETURNS): "4.2.01",
        (RETURN, VAT_PAYABLE): "2.1.02",
        (RETURN, CASH): "1.1.01",
        (RETURN, COGS): "5.1.01",
        (RETURN, INVENTORY): "1.2.01",
        # ------------------------------------------------------- la caja
        (CASH_CLOSE, CASH): "1.1.01",
        (CASH_CLOSE, CASH_OVER): "4.9.01",
        (CASH_CLOSE, CASH_SHORT): "6.9.01",
        (CASH_MOVEMENT, CASH): "1.1.01",
        # ------------------------------------------------------ la compra
        (PURCHASE, INVENTORY): "1.2.01",
        (PURCHASE, VAT_CREDIT): "1.1.05",
        (PURCHASE, PAYABLES): "2.1.01",
        # ------------------------------------------------------- el abono
        (SUPPLIER_PAYMENT, PAYABLES): "2.1.01",
        (SUPPLIER_PAYMENT, CASH): "1.1.01",
        (SUPPLIER_PAYMENT, BANK): "1.1.02",
        # ----------------------------------------------------- la planilla
        (PAYROLL, SALARIES): "6.1.01",
        (PAYROLL, EMPLOYER_CONTRIBUTIONS): "6.1.02",
        (PAYROLL, INCOME_TAX_PAYABLE): "2.1.03",
        (PAYROLL, SOCIAL_SECURITY_PAYABLE): "2.1.04",
        (PAYROLL, SALARIES_PAYABLE): "2.1.05",
        (PAYROLL, OTHER_DEDUCTIONS_PAYABLE): "2.1.06",
    }
    # Una cuenta de ingresos por tarifa. Se generan del mismo sitio del que sale
    # el papel (`sales_role`), para que no puedan discrepar: escritas a mano, un
    # 'sales_13' contra un 'sales_13.0' mandaría al limbo las ventas al 13 %.
    for codigo, tarifa in SALES_ACCOUNTS:
        mapeo[(SALE, sales_role(tarifa))] = codigo
    return mapeo


#: Los papeles que se dejan **sin mapear a propósito**, con su razón.
#:
#: No son un descuido: los dos significan «el sistema no sabe», y una cuenta por
#: omisión sería una respuesta inventada. Caen en 1.9.99, se ven en rojo, y el
#: contador los resuelve reclasificando, que es donde sí se sabe.
UNMAPPED_ON_PURPOSE: dict[str, tuple[str, ...]] = {
    # De dónde salieron los ₡5 000 que entraron a la gaveta. Lo sabe quien los
    # metió, no el sistema.
    CASH_MOVEMENT: (COUNTERPART,),
    # Un abono por «otro» medio —un cheque, una compensación—. Suponer banco
    # dejaría el saldo del libro en desacuerdo con el del banco.
    SUPPLIER_PAYMENT: (UNCLASSIFIED,),
    # Un método de pago que no está en la lista: una venta anterior a T-1104.
    SALE: (UNCLASSIFIED,),
}


# ------------------------------------------------------- qué se le puede hacer


def check_deletable(code: str, *, is_system: bool, lines: int) -> None:
    """Si esa cuenta se puede borrar (RN-64).

    La regla completa es: **de sistema, nunca; con movimientos, tampoco**. Las
    dos razones son distintas y por eso son dos códigos: la primera dice «esta
    cuenta la necesita el programa» y la segunda, «esta cuenta tiene historia».

    Lo que sí se puede con las dos es renombrarlas, porque el mapeo apunta al id
    y no al nombre; y con la segunda, desactivarla.
    """
    if is_system:
        raise AccountIsSystem(code)
    if lines:
        raise AccountInUse(code, lines)


def check_deactivatable(code: str, *, is_system: bool) -> None:
    """Si esa cuenta se puede desactivar (RN-64).

    Una cuenta de sistema desactivada es peor que una borrada: la fila sigue ahí,
    el mapeo la sigue apuntando, y el asiento se escribe contra una cuenta que la
    pantalla ya no ofrece. El problema aparecería semanas después, al buscar por
    qué el catálogo no cuadra con los asientos.
    """
    if is_system:
        raise AccountIsSystem(code)
