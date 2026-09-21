"""
Sucursales y terminales (T-608, RF-26, RN-7, RN-15).

Es el ABM que faltaba desde F2: la compañía nacía con una sucursal y una caja
—las crea `crud_company.dar_de_alta`— y no había forma de agregar la segunda.
Un negocio que abre un local, o que pone otra caja en el mismo, tenía que pedir
que le tocaran la base.

LO QUE NO SE BORRA
------------------

**Una sucursal con ventas se desactiva, no se borra** (RN-7 aplicada acá). Cada
venta, devolución y entrada guarda su `branch_id`, y cada arqueo su
`terminal_id`: borrar la fila dejaría el historial apuntando a la nada, y lo
que se pierde no es la sucursal sino la respuesta a «dónde se vendió esto».
Es la misma decisión que con las categorías en T-403.

Desactivar tampoco es gratis y por eso hay una puerta más: **no se puede dejar a
la compañía sin sucursal activa ni a una sucursal sin caja activa**. Una
compañía que se queda sin caja no puede vender, y el POS lo descubriría en el
peor momento — el error más útil es el que llega cuando alguien está
configurando, no cuando hay un cliente esperando.

LOS LÍMITES DEL PLAN
--------------------

Se cuentan **las activas**, no las filas. Lo que el plan vende es cuántas puede
operar; contar las desactivadas castigaría justamente al que ordena su catálogo
de locales. La contrapartida está escrita y se aplica: **reactivar también
consume cupo**, porque si no, desactivar y reactivar sería la forma de tener
cinco con un plan de tres.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain.errors import InvalidOfficeCode
from app.domain.limits import SIN_LIMITE, hay_lugar
from app.domain.office import BranchCode, TerminalCode
from app.models.model_cash import CashSession
from app.models.model_company import Branch, Terminal
from app.models.model_return import Return
from app.models.model_sales import Sale
from app.models.model_stock_entry import StockEntry
from app.services import crud_company
from app.utils.api_errors import api_error
from app.utils.tenancy import compania_actual


# ------------------------------------------------------------------ comunes


def _codigo(valor: object, tipo: type[BranchCode] | type[TerminalCode]) -> str:
    """El código normalizado, o el «no» con su motivo.

    «1» entra como «001»: quien da de alta una sucursal escribe el número que
    tiene en la cabeza, y el UNIQUE es sobre el texto. Sin normalizar acá, la
    caja 1 y la caja 001 serían dos filas con el mismo número en el comprobante.
    """
    try:
        return str(tipo(valor))
    except InvalidOfficeCode as exc:
        raise api_error(
            400, "invalid_office_code", reason=exc.code, digits=exc.digits
        ) from None


def _plan_actual(db: Session):
    """El plan de la compañía de esta petición, o `None` si no tiene.

    Sin plan no hay límite que aplicar y se deja pasar: es un dato roto en la
    base, y negarle una sucursal a un cliente por un error nuestro sería
    castigarlo por él. El panel de soporte la muestra como compañía sin plan.
    """
    company = crud_company.por_id(db, compania_actual())
    return crud_company.plan_por_id(db, company.plan_id) if company else None


def _cuantas_activas(db: Session, modelo, **filtros) -> int:
    """Cuenta con `func.count`, que es la única forma que se filtra.

    El atajo de `Query` envuelve la consulta en una subconsulta donde el
    criterio de compañía no entra, y contaría las de **todas**. Hay un guardián
    en `tests/test_tenancy.py` que tumba `pytest` si aparece uno sin filtro — y
    que **no tolera esas letras ni en una explicación**, de ahí el rodeo de este
    párrafo. Lo caza también en un comentario, que es lo que hace que la regla
    se aprenda a la primera.
    """
    consulta = db.query(func.count(modelo.id)).filter(modelo.activa.is_(True))
    for campo, valor in filtros.items():
        consulta = consulta.filter(getattr(modelo, campo) == valor)
    return consulta.scalar() or 0


def _sin_lugar(recurso: str, actuales: int, maximo: int):
    return api_error(
        400, "plan_limit_reached", resource=recurso, current=actuales, max=maximo
    )


# --------------------------------------------------------------- sucursales


def sucursales(db: Session) -> list[Branch]:
    """Las de esta compañía, activas y desactivadas.

    Las desactivadas se devuelven **con su estado**, no se esconden: sin verlas,
    reactivar una es imposible desde la pantalla y el código que ocupa parece
    libre hasta que el UNIQUE dice que no. Es lo mismo que hace el árbol de
    categorías desde T-404.
    """
    return db.query(Branch).order_by(Branch.codigo).all()


def crear_sucursal(db: Session, *, codigo: object, nombre: str) -> Branch:
    valor = _codigo(codigo, BranchCode)
    _cabe_otra_sucursal(db)

    if db.query(Branch).filter(Branch.codigo == valor).first():
        raise api_error(409, "branch_code_taken", branch_code=valor)

    # `company_id` no se escribe: lo pone el `before_flush` de `tenancy.py`, el
    # mismo que lo pone en una venta (plan §3.3).
    sucursal = Branch(codigo=valor, nombre=nombre.strip(), activa=True)
    db.add(sucursal)
    db.commit()
    db.refresh(sucursal)
    return sucursal


def _cabe_otra_sucursal(db: Session) -> None:
    plan = _plan_actual(db)
    if plan is None:
        return
    actuales = _cuantas_activas(db, Branch)
    if not hay_lugar(actuales, plan.max_sucursales):
        raise _sin_lugar("branches", actuales, plan.max_sucursales)


def actualizar_sucursal(
    db: Session, branch_id: int, *, nombre: str | None, activa: bool | None
) -> Branch:
    """Renombra y activa o desactiva. **El código no se cambia.**

    Cambiarlo movería el número de todos los comprobantes ya emitidos desde esa
    sucursal, que es justo lo que el consecutivo no puede hacer. Quien se
    equivocó al crearla la desactiva y crea la correcta.
    """
    sucursal = db.query(Branch).filter(Branch.id == branch_id).first()
    if sucursal is None:
        raise api_error(404, "branch_not_found")

    if nombre is not None:
        sucursal.nombre = nombre.strip()

    if activa is not None and activa != sucursal.activa:
        if activa:
            # Reactivar consume cupo: si no, desactivar y reactivar sería la
            # forma de tener cinco sucursales con un plan de tres.
            _cabe_otra_sucursal(db)
        else:
            _ultima_sucursal_no(db, sucursal)
        sucursal.activa = activa
        if not activa:
            # Las cajas de una sucursal apagada no pueden quedar encendidas: el
            # POS las ofrecería y el consecutivo saldría de un local cerrado.
            for terminal in db.query(Terminal).filter(Terminal.branch_id == sucursal.id):
                terminal.activa = False

    db.commit()
    db.refresh(sucursal)
    return sucursal


def _ultima_sucursal_no(db: Session, sucursal: Branch) -> None:
    if not sucursal.activa:
        return
    if _cuantas_activas(db, Branch) <= 1:
        raise api_error(409, "last_active_branch")


def borrar_sucursal(db: Session, branch_id: int) -> None:
    """Borra solo la que no arrastra nada (RN-7).

    Con historia o con cajas colgando responde 409 y dice **las dos cuentas**,
    porque quien lo lee necesita saber qué mover primero.
    """
    sucursal = db.query(Branch).filter(Branch.id == branch_id).first()
    if sucursal is None:
        raise api_error(404, "branch_not_found")

    ventas = _hechos_de_la_sucursal(db, sucursal.id)
    terminales = db.query(func.count(Terminal.id)).filter(
        Terminal.branch_id == sucursal.id
    ).scalar() or 0
    if ventas or terminales:
        raise api_error(409, "branch_in_use", sales=ventas, terminals=terminales)

    _ultima_sucursal_no(db, sucursal)
    db.delete(sucursal)
    db.commit()


def _hechos_de_la_sucursal(db: Session, branch_id: int) -> int:
    """Cuántas filas de negocio la nombran. Ventas, devoluciones y entradas.

    Se suman las tres en un número porque para quien decide son lo mismo:
    historial que se quedaría apuntando a la nada.
    """
    total = 0
    for modelo in (Sale, Return, StockEntry):
        total += (
            db.query(func.count(modelo.id)).filter(modelo.branch_id == branch_id).scalar()
            or 0
        )
    return total


# ---------------------------------------------------------------- terminales


def terminales(db: Session, *, branch_id: int | None = None) -> list[Terminal]:
    consulta = db.query(Terminal)
    if branch_id is not None:
        consulta = consulta.filter(Terminal.branch_id == branch_id)
    return consulta.order_by(Terminal.branch_id, Terminal.codigo).all()


def crear_terminal(db: Session, *, branch_id: int, codigo: object, nombre: str) -> Terminal:
    valor = _codigo(codigo, TerminalCode)

    sucursal = db.query(Branch).filter(Branch.id == branch_id).first()
    if sucursal is None:
        raise api_error(404, "branch_not_found")

    _cabe_otra_terminal(db)

    # El UNIQUE es por sucursal: dos locales pueden tener los dos su «00001».
    ocupado = (
        db.query(Terminal)
        .filter(Terminal.branch_id == branch_id, Terminal.codigo == valor)
        .first()
    )
    if ocupado:
        raise api_error(409, "terminal_code_taken", terminal_code=valor)

    terminal = Terminal(branch_id=branch_id, codigo=valor, nombre=nombre.strip(), activa=True)
    db.add(terminal)
    db.commit()
    db.refresh(terminal)
    return terminal


def _cabe_otra_terminal(db: Session) -> None:
    plan = _plan_actual(db)
    if plan is None:
        return
    # El máximo del plan es **por compañía** y no por sucursal: es lo que dice
    # `plans.max_terminales`, y un techo por sucursal dejaría que un plan de
    # tres cajas tuviera treinta abriendo diez locales.
    actuales = _cuantas_activas(db, Terminal)
    if not hay_lugar(actuales, plan.max_terminales):
        raise _sin_lugar("terminals", actuales, plan.max_terminales)


def actualizar_terminal(
    db: Session, terminal_id: int, *, nombre: str | None, activa: bool | None
) -> Terminal:
    terminal = db.query(Terminal).filter(Terminal.id == terminal_id).first()
    if terminal is None:
        raise api_error(404, "terminal_not_found")

    if nombre is not None:
        terminal.nombre = nombre.strip()

    if activa is not None and activa != terminal.activa:
        if activa:
            _cabe_otra_terminal(db)
        else:
            _ultima_terminal_no(db, terminal)
        terminal.activa = activa

    db.commit()
    db.refresh(terminal)
    return terminal


def _ultima_terminal_no(db: Session, terminal: Terminal) -> None:
    """No se apaga la última caja **de una sucursal activa**.

    Si la sucursal ya está apagada, sus cajas pueden estarlo todas: apagarla es
    justamente lo que las apaga.

    Y una caja **que ya está apagada** no deja a nadie sin caja al irse, así que
    tampoco entra: sin esta línea, borrar la de repuesto —apagada, sin arqueos,
    creada de más— respondía `last_active_terminal` y mandaba a encender una caja
    para poder borrarla. Se ve desde la pantalla y no desde el API, que es donde
    a uno no se le ocurre pedir el borrado de algo que ya no está en uso.
    """
    if not terminal.activa:
        return
    sucursal = db.query(Branch).filter(Branch.id == terminal.branch_id).first()
    if sucursal is None or not sucursal.activa:
        return
    if _cuantas_activas(db, Terminal, branch_id=terminal.branch_id) <= 1:
        raise api_error(409, "last_active_terminal")


def borrar_terminal(db: Session, terminal_id: int) -> None:
    terminal = db.query(Terminal).filter(Terminal.id == terminal_id).first()
    if terminal is None:
        raise api_error(404, "terminal_not_found")

    arqueos = (
        db.query(func.count(CashSession.id))
        .filter(CashSession.terminal_id == terminal.id)
        .scalar()
        or 0
    )
    ventas = (
        db.query(func.count(Sale.id)).filter(Sale.terminal_id == terminal.id).scalar() or 0
    )
    if arqueos or ventas:
        raise api_error(409, "terminal_in_use", sessions=arqueos, sales=ventas)

    _ultima_terminal_no(db, terminal)
    db.delete(terminal)
    db.commit()


# ------------------------------------------------------------------- cupos


def cupos(db: Session) -> dict:
    """Cuántas hay y cuántas permite el plan. Para que la pantalla lo diga.

    Sin esto, el POS solo se entera del techo al chocar con él, y «no cabe otra»
    después de llenar un formulario es peor que «va 3 de 3» antes de abrirlo.
    """
    plan = _plan_actual(db)
    return {
        "branches": _cuantas_activas(db, Branch),
        "max_branches": plan.max_sucursales if plan else SIN_LIMITE,
        "terminals": _cuantas_activas(db, Terminal),
        "max_terminals": plan.max_terminales if plan else SIN_LIMITE,
    }
