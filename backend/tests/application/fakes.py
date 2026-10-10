"""
Repositorios de mentira, en memoria.

Son la prueba de que los puertos sirven para algo: con ellos se puede comprobar
que una venta sin existencias no deja factura fantasma **sin levantar MySQL**,
en milisegundos y sin Docker. Si esto no se pudiera, la lógica seguiría metida
en la capa de persistencia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.application.ports.numbering import Issuer, NumberedDocument, Office
from app.domain.fe_document_type import DEFAULT_ENABLED
from app.domain.money import Money
from app.domain.tax import TaxRate


@dataclass
class FakeProduct:
    id_product: int
    name: str
    price: Money | None
    stock: int
    # `None` es «la tasa configurada del negocio» (RN-9). Por omisión, para que
    # las pruebas anteriores a F5 sigan describiendo el caso de siempre: un
    # catálogo sin tarifas propias.
    tax_rate: TaxRate | None = None
    #: El código de tarifa de Hacienda (RN-76, F7). `None` es «sin clasificar
    #: para factura electrónica», que es lo que tiene un catálogo heredado y lo
    #: que traen las pruebas anteriores a F7.
    tax_code: str | None = None
    #: Lo que cuesta (RN-54, F10). Cero por omisión: es «no se sabe», que es lo
    #: que tienen los productos de las pruebas anteriores a F10 y lo que hace
    #: que la primera compra establezca el costo.
    cost: Money = field(default_factory=Money.zero)
    #: El CABYS y la unidad (RN-86, T-731). Vacíos por omisión, como un
    #: producto que nadie clasificó.
    cabys_code: str | None = None
    unit_of_measure: str | None = None
    #: La partida arancelaria (T-727). Vacía por omisión: un producto que nadie
    #: pensó exportar.
    tariff_heading: str | None = None
    #: Dónde cuelga (RN-6). La 1 por omisión: la categoría de todas las pruebas
    #: que no son de categorías.
    category_id: int = 1
    #: Si alguna venta lo nombra (T-1502): lo dice la prueba, no una venta de verdad.
    sold: bool = False


class FakeProductRepository:
    def __init__(self, productos: list[FakeProduct] | None = None) -> None:
        self.productos = {p.id_product: p for p in (productos or [])}
        self.bloqueados: list[list[int]] = []
        # Códigos de barras ya tomados y productos creados por una entrada.
        self.codigos: dict[str, int] = {}
        self.creados: list[tuple] = []
        #: Lo que la ficha escribió y borró (T-1502).
        self.cambios: list[tuple[int, dict]] = []
        self.borrados: list[int] = []
        self._siguiente = max(self.productos, default=0) + 1

    def get(self, product_id: int) -> FakeProduct | None:
        return self.productos.get(product_id)

    def get_by_barcode(self, barcode: str) -> FakeProduct | None:  # pragma: no cover
        return next((p for p in self.productos.values() if p.name == barcode), None)

    def lock(self, product_ids: list[int]) -> dict[int, FakeProduct]:
        # Se anota qué se bloqueó y en qué orden: una prueba comprueba que se
        # piden ordenados, que es lo que evita el interbloqueo entre dos cajas.
        self.bloqueados.append(list(product_ids))
        return {i: self.productos[i] for i in product_ids if i in self.productos}

    def update_cost(self, product_id: int, cost: Money) -> None:
        self.productos[product_id].cost = cost

    def barcode_taken(self, barcode: str, *, except_product_id: int | None = None) -> bool:
        dueno = self.codigos.get(barcode)
        return dueno is not None and dueno != except_product_id

    def create(
        self,
        *,
        name,
        description,
        price,
        barcode,
        category_id,
        created_at,
        cabys_code=None,
        tax_rate=None,
        tax_code=None,
        unit_of_measure=None,
        tariff_heading=None,
    ) -> int:
        nuevo = FakeProduct(
            self._siguiente,
            name,
            price,
            stock=0,
            tax_rate=tax_rate,
            tax_code=tax_code,
            cabys_code=cabys_code,
            unit_of_measure=unit_of_measure,
            tariff_heading=tariff_heading,
            category_id=category_id,
        )
        self.productos[self._siguiente] = nuevo
        self.codigos[barcode] = self._siguiente
        self.creados.append((name, barcode, price, category_id, created_at))
        self._siguiente += 1
        return nuevo.id_product

    def update(self, product_id: int, changes: dict) -> None:
        self.cambios.append((product_id, dict(changes)))
        producto = self.productos[product_id]
        for clave, valor in changes.items():
            if hasattr(producto, clave):
                setattr(producto, clave, valor)

    def delete(self, product_id: int) -> None:
        self.borrados.append(product_id)
        del self.productos[product_id]

    def has_sales(self, product_id: int) -> bool:
        return self.productos[product_id].sold


@dataclass
class FakeCategory:
    """Una categoría vista desde la ficha (RN-6). Hoja activa y raíz por omisión."""

    id: int
    name: str
    is_active: bool = True
    active_children: int = 0
    #: La madre (RN-5): nula en las raíces. Lo usa la toma física (T-1503).
    parent_id: int | None = None


class FakeCategoryRepository:
    def __init__(self, categorias: list[FakeCategory] | None = None) -> None:
        self.categorias = {c.id: c for c in (categorias or [FakeCategory(1, "General")])}

    def get(self, category_id: int) -> FakeCategory | None:
        return self.categorias.get(category_id)

    def tree(self) -> dict[int, int | None]:
        return {c.id: c.parent_id for c in self.categorias.values()}


@dataclass
class FilaDeToma:
    id: int
    branch_id: int
    category_id: int | None
    opened_by: int
    opened_at: datetime
    notes: str | None
    status: str = "open"
    closed_by: int | None = None
    closed_at: datetime | None = None


@dataclass
class LineaContada:
    product_id: int
    lot_id: int | None
    system_qty: int
    counted_qty: int
    counted_at: datetime
    counted_by: int


class FakeStockCountRepository:
    """Las tomas y sus líneas, en memoria (T-1503)."""

    def __init__(self) -> None:
        self.tomas: list[FilaDeToma] = []
        self.lineas: dict[int, list[LineaContada]] = {}
        self._siguiente = 1

    def get(self, count_id: int) -> FilaDeToma | None:
        return next((t for t in self.tomas if t.id == count_id), None)

    def open_in_branch(self, branch_id: int) -> list[FilaDeToma]:
        return [t for t in self.tomas if t.branch_id == branch_id and t.status == "open"]

    def add(self, **datos) -> int:
        toma = FilaDeToma(id=self._siguiente, **datos)
        self._siguiente += 1
        self.tomas.append(toma)
        self.lineas[toma.id] = []
        return toma.id

    def lines_of(self, count_id: int) -> list[LineaContada]:
        return list(self.lineas.get(count_id, []))

    def record_line(self, count_id: int, **datos) -> None:
        lineas = self.lineas.setdefault(count_id, [])
        nueva = LineaContada(**datos)
        # Volver a contar el mismo (producto, lote) reemplaza, no suma.
        for i, linea in enumerate(lineas):
            if linea.product_id == nueva.product_id and linea.lot_id == nueva.lot_id:
                lineas[i] = nueva
                return
        lineas.append(nueva)

    def close(self, count_id: int, *, status: str, closed_by: int, closed_at: datetime) -> None:
        toma = self.get(count_id)
        toma.status = status
        toma.closed_by = closed_by
        toma.closed_at = closed_at


#: La sucursal de todas las pruebas que no son de sucursales (F15).
SUCURSAL = 1


class FakeStockLevelRepository:
    """La existencia por sucursal, en memoria (T-1502).

    Nace vacía y **se siembra sola** la primera vez que se bloquea un producto
    en `SUCURSAL`: lo que el producto tenga en `stock` y no esté ya en otra
    sucursal es lo que hay en la de siempre. Así las pruebas anteriores a F15
    —que arman un catálogo con `stock=110` y nada más— siguen describiendo el
    mismo mundo: un solo local con todo adentro. Cualquier otra sucursal nace
    en cero, que es lo que RN-102 dice de un local al que nada ha entrado.
    """

    def __init__(self, productos: FakeProductRepository) -> None:
        self._productos = productos
        self.niveles: dict[tuple[int, int], int] = {}
        #: En qué orden se bloquearon, para comprobar que el producto va antes.
        self.bloqueados: list[tuple[int, int]] = []

    def lock(self, product_id: int, branch_id: int) -> int:
        self.bloqueados.append((product_id, branch_id))
        if (product_id, branch_id) not in self.niveles:
            en_otras = sum(q for (p, _), q in self.niveles.items() if p == product_id)
            sembrado = self._productos.productos[product_id].stock - en_otras
            self.niveles[(product_id, branch_id)] = sembrado if branch_id == SUCURSAL else 0
        return self.niveles[(product_id, branch_id)]

    def set(self, product_id: int, branch_id: int, quantity: int) -> None:
        self.niveles[(product_id, branch_id)] = quantity

    def levels_of(self, product_id: int) -> dict[int, int]:
        return {b: q for (p, b), q in self.niveles.items() if p == product_id}

    def levels_in(self, branch_id: int) -> dict[int, int]:
        return {p: q for (p, b), q in self.niveles.items() if b == branch_id}

    def add_to_total(self, product_id: int, delta: int) -> None:
        self._productos.productos[product_id].stock += delta


class FakeKardex:
    """El kárdex en memoria: escribe y lee."""

    def __init__(self) -> None:
        self.movimientos: list = []

    def record(self, movement) -> int:
        from dataclasses import replace

        anotado = replace(movement, id=len(self.movimientos) + 1)
        self.movimientos.append(anotado)
        return anotado.id

    def of_product(self, product_id: int, *, branch_id=None, since=None, until=None) -> list:
        return [
            m
            for m in reversed(self.movimientos)
            if m.product_id == product_id
            and (branch_id is None or m.branch_id == branch_id)
            and (since is None or m.moved_at >= since)
            and (until is None or m.moved_at <= until)
        ]

    def of_source(self, source_type: str, source_id: int) -> list:
        return [
            m for m in self.movimientos if m.source_type == source_type and m.source_id == source_id
        ]

    def count_for(self, product_id: int) -> int:
        return sum(1 for m in self.movimientos if m.product_id == product_id)


@dataclass
class FakeReason:
    """Un motivo de salida (RN-99). Activo y de la compañía por omisión."""

    id: int
    code: str
    name: str
    is_system: bool = False
    is_active: bool = True


class FakeStockReasonRepository:
    def __init__(self, motivos: list[FakeReason] | None = None) -> None:
        self.motivos = {m.id: m for m in (motivos or [])}

    def get(self, reason_id: int) -> FakeReason | None:
        return self.motivos.get(reason_id)


@dataclass
class FilaDeSalida:
    id: int
    branch_id: int
    reason_id: int
    user_id: int
    notes: str | None
    total_cost: Money
    created_at: datetime
    lines: list
    status: str = "applied"
    voided_at: datetime | None = None
    void_reason: str | None = None


class FakeStockExitRepository:
    def __init__(self) -> None:
        self.salidas: list[FilaDeSalida] = []
        self._siguiente = 1

    def get(self, exit_id: int) -> FilaDeSalida | None:
        return next((s for s in self.salidas if s.id == exit_id), None)

    def add(self, **datos) -> int:
        salida = FilaDeSalida(id=self._siguiente, **datos)
        self._siguiente += 1
        self.salidas.append(salida)
        return salida.id

    def lines_of(self, exit_id: int) -> list:
        salida = self.get(exit_id)
        return salida.lines if salida else []

    def mark_voided(self, exit_id: int, *, voided_at: datetime, reason: str) -> None:
        salida = self.get(exit_id)
        salida.status = "voided"
        salida.voided_at = voided_at
        salida.void_reason = reason


def mover(productos: FakeProductRepository, kardex: FakeKardex | None = None):
    """`MoveStock` armado con sus dobles, sobre ESTE catálogo.

    Devuelve también los niveles y el kárdex, que es lo que las pruebas miran.
    Las que no miran el inventario pasan solo el catálogo y se quedan con el
    primer valor.
    """
    from app.application.use_cases.move_stock import MoveStock

    niveles = FakeStockLevelRepository(productos)
    bitacora = kardex or FakeKardex()
    return MoveStock(products=productos, levels=niveles, kardex=bitacora), niveles, bitacora


@dataclass
class FilaDeVenta:
    id_sale: int
    sale_number: str
    client_id: int | None
    user_id: int
    subtotal: Money
    tax: Money
    total: Money
    payment_method: str
    cash_received: Money
    change_given: Money
    created_at: datetime
    lines: list
    document_type: str | None = None
    #: Dónde se cobró (F15). La sucursal de siempre si la prueba no lo dice.
    branch_id: int = SUCURSAL


@dataclass
class FakeClient:
    """Un cliente visto desde la venta: quién es ante Hacienda (T-727)."""

    id_client: int
    identification_type: str | None = None
    foreign_address: str | None = None


class FakeClientRepository:
    """Los clientes de **esta** compañía, por id. Los demás no existen.

    Se construye con ids —clientes del país sin más datos, que es lo que
    describen las pruebas anteriores a T-727— o con `FakeClient`.
    """

    def __init__(
        self, ids: set[int] | None = None, clientes: list[FakeClient] | None = None
    ) -> None:
        self.clientes = {i: FakeClient(i) for i in (ids or ())}
        self.clientes.update({c.id_client: c for c in (clientes or [])})

    def get(self, client_id: int) -> FakeClient | None:
        return self.clientes.get(client_id)


class FakeSaleRepository:
    def __init__(self) -> None:
        self.ventas: list[FilaDeVenta] = []
        self._siguiente = 1

    def add(self, **datos) -> int:
        id_sale = self._siguiente
        self._siguiente += 1
        self.ventas.append(FilaDeVenta(id_sale=id_sale, **datos))
        return id_sale

    def get(self, sale_id: int):  # pragma: no cover
        return next((v for v in self.ventas if v.id_sale == sale_id), None)

    def exists_with_number(self, sale_number: str) -> bool:
        return any(v.sale_number == sale_number for v in self.ventas)

    def sold_quantities(self, sale_id: int) -> dict[int, int]:
        venta = self.get(sale_id)
        return {l.product_id: l.quantity for l in venta.lines} if venta else {}

    def sold_prices(self, sale_id: int) -> dict[int, Money]:
        venta = self.get(sale_id)
        return {l.product_id: l.unit_price for l in venta.lines} if venta else {}

    def sold_costs(self, sale_id: int) -> dict[int, Money]:
        """El costo congelado de cada línea, para las que lo tengan (RN-63).

        Se salta las que lo traen en nulo —ventas anteriores a F11, productos
        que nunca se compraron—: el asiento de esa devolución no lleva el par
        costo / inventario en vez de inventar un cero.
        """
        venta = self.get(sale_id)
        if venta is None:
            return {}
        return {
            l.product_id: l.unit_cost for l in venta.lines if l.unit_cost is not None
        }

    def sold_tax_rates(self, sale_id: int) -> dict[int, TaxRate]:
        """La tarifa congelada de cada línea, para las que la tengan.

        Se salta las que la traen en nulo, que es como quedan las ventas
        anteriores a la migración 006: quien llama cae al cociente del
        encabezado, que en ellas es exacto.
        """
        venta = self.get(sale_id)
        if venta is None:
            return {}
        return {
            l.product_id: l.tax_rate for l in venta.lines if l.tax_rate is not None
        }

    def in_window(self, user_id: int, start: datetime, end: datetime) -> list:
        return [
            v for v in self.ventas if v.user_id == user_id and start <= v.created_at <= end
        ]


@dataclass
class FilaDeDevolucion:
    id_return: int
    sale_id: int
    user_id: int
    reason: str
    # Desde F5 la devolución guarda su desglose: con tarifas mezcladas el
    # impuesto no se deduce del total.
    subtotal: Money
    tax: Money
    total: Money
    created_at: datetime
    lines: list
    #: La nota de crédito (RN-89). Nulos cuando la venta no fue comprobante.
    document_type: str | None = None
    reference_code: str | None = None
    #: Dónde se devolvió (F15): ahí se repone.
    branch_id: int = SUCURSAL


class FakeReturnRepository:
    def __init__(self) -> None:
        self.devoluciones: list[FilaDeDevolucion] = []
        self._siguiente = 1

    def returned_quantities(self, sale_id: int) -> dict[int, int]:
        totales: dict[int, int] = {}
        for d in self.devoluciones:
            if d.sale_id != sale_id:
                continue
            for l in d.lines:
                totales[l.product_id] = totales.get(l.product_id, 0) + l.quantity
        return totales

    def add(self, **datos) -> int:
        id_return = self._siguiente
        self._siguiente += 1
        self.devoluciones.append(FilaDeDevolucion(id_return=id_return, **datos))
        return id_return

    def total_in_window(self, user_id: int, start: datetime, end: datetime) -> Money:
        return Money.sum(
            d.total
            for d in self.devoluciones
            if d.user_id == user_id and start <= d.created_at <= end
        )


@dataclass
class FilaDeNota:
    """Una nota por monto (T-726): la ND o la NC que no mueve mercadería."""

    id_note: int
    sale_id: int
    user_id: int
    document_type: str
    reference_code: str
    reason: str
    payment_method: str | None
    subtotal: Money
    tax: Money
    total: Money
    created_at: datetime
    lines: list


class FakeNoteRepository:
    def __init__(self) -> None:
        self.notas: list[FilaDeNota] = []
        self._siguiente = 1

    def adjustments(self, sale_id: int) -> dict[int, tuple[Money, Money]]:
        ajustes: dict[int, tuple[Money, Money]] = {}
        for n in self.notas:
            if n.sale_id != sale_id:
                continue
            for l in n.lines:
                sumado, restado = ajustes.get(l.product_id, (Money.zero(), Money.zero()))
                if n.document_type == "02":
                    sumado = sumado + l.total
                else:
                    restado = restado + l.total
                ajustes[l.product_id] = (sumado, restado)
        return ajustes

    def add(self, **datos) -> int:
        id_note = self._siguiente
        self._siguiente += 1
        self.notas.append(FilaDeNota(id_note=id_note, **datos))
        return id_note

    def in_window(self, user_id: int, start: datetime, end: datetime) -> list:
        return [
            n for n in self.notas if n.user_id == user_id and start <= n.created_at <= end
        ]


@dataclass
class FilaDeTurno:
    id: int
    user_id: int
    opening_amount: Money
    opened_at: datetime
    closed_at: datetime | None = None
    closing_amount: Money | None = None
    status: str = "abierta"
    notes: str | None = None


@dataclass
class FilaDeMovimiento:
    id: int
    session_id: int
    type: str
    amount: Money
    reason: str
    created_at: datetime


class FakeCashRepository:
    def __init__(self) -> None:
        self.turnos: list[FilaDeTurno] = []
        self.movimientos: list[FilaDeMovimiento] = []
        self._siguiente = 1
        self._siguiente_mov = 1

    def open_session(self, user_id: int) -> FilaDeTurno | None:
        return next(
            (t for t in self.turnos if t.user_id == user_id and t.status == "abierta"), None
        )

    def create_session(self, *, user_id, opening, opened_at, notes) -> FilaDeTurno:
        turno = FilaDeTurno(
            id=self._siguiente,
            user_id=user_id,
            opening_amount=opening,
            opened_at=opened_at,
            notes=notes,
        )
        self._siguiente += 1
        self.turnos.append(turno)
        return turno

    def close_session(self, session_id: int, *, counted, closed_at, notes) -> FilaDeTurno:
        turno = next(t for t in self.turnos if t.id == session_id)
        turno.closing_amount = counted
        turno.closed_at = closed_at
        turno.status = "cerrada"
        if notes:
            turno.notes = notes
        return turno

    def add_movement(self, *, session_id, type_, amount, reason, created_at):
        mov = FilaDeMovimiento(
            id=self._siguiente_mov,
            session_id=session_id,
            type=type_,
            amount=amount,
            reason=reason,
            created_at=created_at,
        )
        self._siguiente_mov += 1
        self.movimientos.append(mov)
        return mov

    def movements(self, session_id: int) -> list:
        return [m for m in self.movimientos if m.session_id == session_id]


@dataclass
class FilaDeEntrada:
    id: int
    document_number: str | None
    supplier: str | None
    source: str
    user_id: int
    notes: str | None
    total_cost: Money
    created_at: datetime
    lines: list
    status: str = "aplicada"
    # Lo de F10. Con todo en su valor de reposo esto es una entrada de las de
    # siempre, que es lo que siguen siendo las de las pruebas anteriores.
    supplier_id: int | None = None
    document_key: str | None = None
    document_date: object = None
    payment_terms: str = "cash"
    due_date: object = None
    subtotal: Money | None = None
    tax: Money | None = None
    #: La factura de compra (T-728); nula en toda compra a un proveedor inscrito.
    document_type: str | None = None
    #: A qué sucursal entró (F15): de ahí sale al anular.
    branch_id: int = SUCURSAL


class FakeStockEntryRepository:
    def __init__(self) -> None:
        self.entradas: list[FilaDeEntrada] = []
        self._siguiente = 1

    def get(self, entry_id: int) -> FilaDeEntrada | None:
        return next((e for e in self.entradas if e.id == entry_id), None)

    def applied_with_document(
        self, document_number: str, supplier_id: int | None = None
    ) -> FilaDeEntrada | None:
        # Por proveedor desde F10: la factura 1234 de un mayorista no es la 1234
        # de otro, y sin proveedor se compara contra las que tampoco lo tienen.
        return next(
            (
                e
                for e in self.entradas
                if e.document_number == document_number
                and e.status == "aplicada"
                and e.supplier_id == supplier_id
            ),
            None,
        )

    def add(self, **datos) -> int:
        entrada = FilaDeEntrada(id=self._siguiente, **datos)
        self._siguiente += 1
        self.entradas.append(entrada)
        return entrada.id

    def lines_of(self, entry_id: int) -> list:
        entrada = self.get(entry_id)
        return entrada.lines if entrada else []

    def mark_cancelled(self, entry_id: int) -> None:
        self.get(entry_id).status = "anulada"


@dataclass
class FilaDeAbono:
    id: int
    supplier_id: int
    entry_id: int
    amount: Money
    method: str
    reference: str | None
    cash_movement_id: int | None
    user_id: int
    paid_at: datetime


class FakeSupplierPaymentRepository:
    def __init__(self) -> None:
        self.abonos: list[FilaDeAbono] = []
        self._siguiente = 1

    def amounts_for(self, entry_id: int) -> list[Money]:
        return [a.amount for a in self.abonos if a.entry_id == entry_id]

    def add(self, **datos) -> int:
        abono = FilaDeAbono(id=self._siguiente, **datos)
        self._siguiente += 1
        self.abonos.append(abono)
        return abono.id


class FakeSettingsRepository:
    """La configuración que lee la venta, sin tabla `settings` de por medio."""

    def __init__(
        self, *, einvoicing: bool = False, document_types: frozenset[str] | None = None
    ) -> None:
        # Apagada por omisión: es lo que tiene toda compañía hasta que el dueño
        # la activa, y lo que describen las pruebas anteriores a RN-85.
        self._einvoicing = einvoicing
        # Los de fábrica por omisión (RN-88), que es con lo que nace toda compañía.
        self._document_types = document_types if document_types is not None else DEFAULT_ENABLED

    def einvoicing_enabled(self) -> bool:
        return self._einvoicing

    def document_types(self) -> frozenset[str]:
        return self._document_types


class FakeUnitOfWork:
    """Lleva la cuenta de si se confirmó o se revirtió."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.entradas = 0

    def __enter__(self) -> FakeUnitOfWork:
        self.entradas += 1
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self.rollback()
        return False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class FakeDocumentStore:
    """El almacén de comprobantes, en memoria (T-623).

    Implementa el mismo contrato que el adaptador de S3 y lo demuestra: los dos
    pasan la batería de `tests/test_almacen_documentos.py`. Lo que importa que
    replique no es guardar —eso es un diccionario— sino **negarse a pisar** lo
    ya escrito, que es la regla de la que depende que una firma siga valiendo.
    """

    def __init__(self) -> None:
        self.contenido: dict[str, bytes] = {}

    def put(self, ref, content: bytes) -> str:
        from app.application.ports.documents import DocumentAlreadyStored

        if ref.key in self.contenido:
            raise DocumentAlreadyStored(ref.key)
        self.contenido[ref.key] = bytes(content)
        return ref.key

    def get(self, ref) -> bytes:
        from app.application.ports.documents import DocumentNotFound

        if ref.key not in self.contenido:
            raise DocumentNotFound(ref.key)
        return self.contenido[ref.key]

    def exists(self, ref) -> bool:
        return ref.key in self.contenido


class FakeSecretBox:
    """El cifrado en reposo, sin cifrar nada (T-602a).

    **No cifra, y es a propósito**: lo que un doble tiene que replicar no es el
    AES sino **la regla** —que un valor sellado para una compañía y un ambiente
    no se abra con otros—, porque es lo único que un caso de uso puede notar.
    Un doble que cifrara de verdad sería un segundo adaptador con sus propios
    defectos.

    Nunca sale de `tests/`. Si apareciera importado desde `app/`, lo que habría
    es una credencial guardada en claro.
    """

    def encrypt(self, plaintext: str, *, company_id: int, environment: str) -> str:
        return f"{company_id}:{environment}|{plaintext}"

    def decrypt(self, sealed: str, *, company_id: int, environment: str) -> str:
        from app.application.ports.secrets import SecretUnreadable

        prefijo = f"{company_id}:{environment}|"
        if not sealed.startswith(prefijo):
            raise SecretUnreadable("no abre con esta compañía y este ambiente")
        return sealed[len(prefijo):]


class FakeDocumentSigner:
    """El firmante, con las llaves en memoria (T-602).

    **Firma de verdad**, y tiene que hacerlo: lo que un caso de uso comprueba de
    un firmante es que lo firmado verifique con el certificado público, y un
    doble que devolviera bytes fijos dejaría pasar cualquier error de a quién
    pertenece la llave.

    Lo que NO replica es lo que hace valioso a Vault —que la privada no pase por
    la memoria de la aplicación—, y por eso vive en `tests/` y no en `app/`.
    """

    def __init__(self) -> None:
        self.llaves: dict[tuple[int, str], object] = {}

    def import_key(self, pkcs8_der: bytes, *, company_id: int, environment: str) -> None:
        from cryptography.hazmat.primitives import serialization

        from app.domain.hacienda import check_environment

        check_environment(environment)
        self.llaves[(company_id, environment)] = serialization.load_der_private_key(
            pkcs8_der, password=None
        )

    def sign(self, digest: bytes, *, company_id: int, environment: str) -> bytes:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.asymmetric import utils as asimetrico

        from app.application.ports.signing import SigningKeyMissing

        llave = self.llaves.get((company_id, environment))
        if llave is None:
            raise SigningKeyMissing(company_id, environment)
        return llave.sign(
            digest, padding.PKCS1v15(), asimetrico.Prehashed(hashes.SHA256())
        )

    def forget_key(self, *, company_id: int, environment: str) -> None:
        # Quitar lo que no está no es un error: es el estado que se pedía.
        self.llaves.pop((company_id, environment), None)


@dataclass
class FilaDeCredenciales:
    """Una fila de `fe_credentials`, con las dos mitades separadas.

    Nace **vacía de las dos**: es como está un ambiente que nunca se configuró,
    y lo que importa probar es justamente que cada mitad se pueda llenar sin
    tocar la otra.
    """

    environment: str
    certificate_pem: str | None = None
    certificate_name: str | None = None
    expires_at: datetime | None = None
    cert_uploaded_at: datetime | None = None
    cert_uploaded_by: int | None = None
    key_custody: str | None = None
    atv_user: str | None = None
    atv_password_encrypted: str | None = None
    atv_updated_at: datetime | None = None
    atv_updated_by: int | None = None
    atv_verified_at: datetime | None = None


class FakeFeCredentialsRepository:
    """Las credenciales de Hacienda, en memoria (T-603)."""

    def __init__(self, filas: list[FilaDeCredenciales] | None = None) -> None:
        self.filas = {f.environment: f for f in (filas or [])}

    def _fila(self, environment: str) -> FilaDeCredenciales:
        if environment not in self.filas:
            self.filas[environment] = FilaDeCredenciales(environment=environment)
        return self.filas[environment]

    def get(self, environment: str) -> FilaDeCredenciales | None:
        return self.filas.get(environment)

    def all(self) -> list[FilaDeCredenciales]:
        return list(self.filas.values())

    def save_certificate(
        self,
        *,
        environment: str,
        certificate_pem: str,
        certificate_name: str,
        expires_at: datetime,
        uploaded_at: datetime,
        uploaded_by: int,
    ) -> None:
        fila = self._fila(environment)
        fila.certificate_pem = certificate_pem
        fila.certificate_name = certificate_name
        fila.expires_at = expires_at
        fila.cert_uploaded_at = uploaded_at
        fila.cert_uploaded_by = uploaded_by
        fila.key_custody = "vault"

    def clear_certificate(self, *, environment: str) -> None:
        fila = self._fila(environment)
        fila.certificate_pem = None
        fila.certificate_name = None
        fila.expires_at = None
        fila.cert_uploaded_at = None
        fila.cert_uploaded_by = None
        fila.key_custody = None

    def save_atv(
        self,
        *,
        environment: str,
        user: str,
        password_encrypted: str,
        updated_at: datetime,
        updated_by: int,
    ) -> None:
        fila = self._fila(environment)
        fila.atv_user = user
        fila.atv_password_encrypted = password_encrypted
        fila.atv_updated_at = updated_at
        fila.atv_updated_by = updated_by
        # Cambiar la contraseña invalida la verificación anterior: son otras
        # credenciales. Sin esto la pantalla seguiría diciendo «verificadas el 3
        # de septiembre» sobre algo que se cambió hoy y que nadie probó.
        fila.atv_verified_at = None

    def set_verified(self, *, environment: str, at: datetime | None) -> None:
        self._fila(environment).atv_verified_at = at


class FakeHaciendaIdp:
    """El IdP de Hacienda, sin red (T-612).

    Se le dice de antemano qué va a contestar, porque **los tres desenlaces de
    RF-31 no se pueden provocar contra el de verdad**: «credenciales malas» sí,
    pero «Hacienda caída» hay que esperar a que pase. Un adaptador que solo se
    probara en vivo tendría dos de los tres caminos sin ejercitar nunca, y el
    que faltaría es justo el que se confunde.
    """

    def __init__(self, *, falla: Exception | None = None, token: str = "tok-123") -> None:
        self.falla = falla
        self.token_devuelto = token
        #: Con qué se le llamó. Que la contraseña llegue **descifrada** es la
        #: mitad del trabajo del caso de uso, y sin mirarlo no se vería.
        self.llamadas: list[tuple] = []

    def token(self, endpoints, *, user: str, password: str) -> str:
        self.llamadas.append((endpoints, user, password))
        if self.falla is not None:
            raise self.falla
        return self.token_devuelto


@dataclass
class CertificadoLeido:
    certificate_pem: str
    private_key_der: bytes
    subject: str
    expires_at: datetime


class FakeCertificateReader:
    """Abre un `.p12` de mentira (T-603).

    El formato es `b"P12|<pin>|<sujeto>|<iso del vencimiento>"`, y la llave que
    devuelve es de verdad porque el firmante la va a usar. Lo que replica es lo
    único que le importa al caso de uso: **que el PIN tiene que coincidir**.
    """

    def __init__(self, private_key_der: bytes, *, pin: str = "1234") -> None:
        self.private_key_der = private_key_der
        self.pin = pin
        self.leidos = 0

    def read(self, p12: bytes, pin: str):
        from app.application.ports.signing import InvalidCertificate

        self.leidos += 1
        if not p12.startswith(b"P12|"):
            raise InvalidCertificate("not_a_p12")
        if pin != self.pin:
            raise InvalidCertificate("bad_pin")

        _, _, sujeto, vence = p12.decode("utf-8").split("|")
        return CertificadoLeido(
            certificate_pem="-----BEGIN CERTIFICATE-----\nfingido\n-----END CERTIFICATE-----",
            private_key_der=self.private_key_der,
            subject=sujeto,
            expires_at=datetime.fromisoformat(vence),
        )


class FakeIssuerRepository:
    """El emisor de la numeración (T-705). Por omisión, el de la factura de
    referencia del usuario: jurídica, en pruebas."""

    def __init__(
        self,
        identification: str | None = "3101702934",
        *,
        environment: str = "sandbox",
        economic_activity: str | None = "474100",
    ) -> None:
        self.emisor = Issuer(
            identification=identification,
            environment=environment,
            economic_activity=economic_activity,
        )

    def issuer(self) -> Issuer:
        return self.emisor


class FakeDocumentNumbering:
    """El contador y los comprobantes numerados, en memoria (T-704).

    Lleva la cuenta de qué series se bloquearon, para poder decir que una venta
    que no llegó a numerarse no tocó el contador.
    """

    def __init__(self, office: Office | None = None, series: dict | None = None) -> None:
        self._office = office or Office(branch_code="001", terminal_code="00001")
        #: (tipo, ambiente) → última secuencia.
        self.series: dict[tuple[str, str], int] = dict(series or {})
        self.bloqueadas: list[tuple[str, str]] = []
        self.comprobantes: list[NumberedDocument] = []

    def office(self) -> Office:
        return self._office

    def last_sequence(self, *, document_type: str, environment: str) -> int:
        self.bloqueadas.append((document_type, environment))
        return self.series.get((document_type, environment), 0)

    def save_sequence(self, *, document_type: str, environment: str, value: int) -> None:
        self.series[(document_type, environment)] = value

    def record(self, document: NumberedDocument) -> None:
        self.comprobantes.append(document)


class FakeSecurityCodes:
    """Códigos de seguridad predecibles: 00000001, 00000002…"""

    def __init__(self) -> None:
        self.entregados = 0

    def new(self) -> str:
        self.entregados += 1
        return f"{self.entregados:08d}"


def numerador(
    issuer: FakeIssuerRepository | None = None,
    numbering: FakeDocumentNumbering | None = None,
):
    """La numeración armada con sus dobles. Devuelve también el contador, que es
    lo que las pruebas miran."""
    from app.application.use_cases.number_document import NumberDocument

    contador = numbering or FakeDocumentNumbering()
    return (
        NumberDocument(
            issuer=issuer or FakeIssuerRepository(),
            numbering=contador,
            security_codes=FakeSecurityCodes(),
        ),
        contador,
    )


# ------------------------------------------------------- el recorrido (F7)


def documento(**cambios):
    """Un comprobante numerado, como lo ve el recorrido. Lo que no se diga es
    el de una venta recién numerada, sin firmar ni enviar."""
    from datetime import datetime

    from app.application.ports.fe_documents import DocumentSnapshot

    base = dict(
        id=1,
        company_id=1,
        source_type="sale",
        source_id=50,
        document_type="04",
        environment="sandbox",
        clave="50603102600310170293400100001040000000001159971093",
        consecutive="00100001040000000001",
        situation="1",
        issued_at=datetime(2026, 10, 3, 0, 13, 39),
        status="numbered",
        next_attempt_at=datetime(2026, 10, 3, 0, 13, 39),
    )
    return DocumentSnapshot(**{**base, **cambios})


class FakeTransmissionRepository:
    """`fe_documents` y su bitácora, en memoria.

    Lo que importa que replique es lo que la cola mira: qué está pendiente y le
    toca ya, y que `update` escriba solo lo nombrado —un paso que falla no
    puede borrar el `signed_at` de otro—.
    """

    def __init__(self, docs=(), *, salud=None) -> None:
        from app.application.ports.fe_documents import TransmissionHealth

        self.docs = {d.id: d for d in docs}
        self.eventos: dict[int, list] = {}
        self.salud = salud or TransmissionHealth(None, None)

    def get(self, document_id: int):
        return self.docs.get(document_id)

    def latest_for(self, source_type: str, source_id: int):
        candidatos = [
            d for d in self.docs.values() if d.source_type == source_type and d.source_id == source_id
        ]
        return max(candidatos, key=lambda d: d.id) if candidatos else None

    def due(self, now, *, limit: int):
        from app.domain.fe_transmission import PENDING

        listos = [
            d
            for d in self.docs.values()
            if d.status in PENDING and d.next_attempt_at is not None and d.next_attempt_at <= now
        ]
        listos.sort(key=lambda d: (d.next_attempt_at, d.id))
        return listos[:limit]

    def update(self, document_id: int, change):
        from dataclasses import replace

        actual = replace(self.docs[document_id], **change.fields())
        self.docs[document_id] = actual
        return actual

    def add_event(self, document_id: int, event) -> None:
        self.eventos.setdefault(document_id, []).append(event)

    def events(self, document_id: int):
        return list(self.eventos.get(document_id, []))

    def health(self):
        return self.salud

    def stopped(self):
        return sorted(
            (d for d in self.docs.values() if d.status == "stopped"),
            key=lambda d: (d.issued_at, d.id),
        )

    def counts(self):
        from app.application.ports.fe_documents import QueueCounts
        from app.domain.fe_transmission import PENDING

        por_estado: dict[str, int] = {}
        for d in self.docs.values():
            por_estado[d.status] = por_estado.get(d.status, 0) + 1
        pendientes = [d.issued_at for d in self.docs.values() if d.status in PENDING]
        return QueueCounts(by_status=por_estado, oldest_pending_at=min(pendientes) if pendientes else None)

    def accepted_by_type(self, environment: str):
        cuenta: dict[str, int] = {}
        for d in self.docs.values():
            if d.status == "accepted" and d.environment == environment:
                cuenta[d.document_type] = cuenta.get(d.document_type, 0) + 1
        return cuenta


class FakeHaciendaReception:
    """La recepción de Hacienda, con las respuestas escritas de antemano.

    `envios` y `consultas` son colas: cada llamada saca la siguiente, que es
    `None` (202) o una excepción para `submit`, y un `Verdict` o una excepción
    para `status`. Lo que se le mandó queda en `payloads` y `tokens`.
    """

    def __init__(self, *, envios=(), consultas=()) -> None:
        self.envios = list(envios)
        self.consultas = list(consultas)
        self.payloads: list[dict] = []
        self.tokens: list[str] = []
        self.claves: list[str] = []

    def submit(self, endpoints, *, token: str, payload) -> None:
        self.tokens.append(token)
        self.payloads.append(dict(payload))
        siguiente = self.envios.pop(0) if self.envios else None
        if isinstance(siguiente, Exception):
            raise siguiente

    def status(self, endpoints, *, token: str, clave: str):
        from app.application.ports.transmission import Verdict

        self.tokens.append(token)
        self.claves.append(clave)
        siguiente = self.consultas.pop(0) if self.consultas else Verdict("aceptado")
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente


class FakeComprobanteSource:
    """Arma siempre el mismo comprobante, o falla como se le diga."""

    def __init__(self, comprobante=None, *, falla: Exception | None = None) -> None:
        self._comprobante = comprobante
        self._falla = falla
        self.pedidos: list[int] = []

    def comprobante(self, document):
        self.pedidos.append(document.id)
        if self._falla is not None:
            raise self._falla
        return self._comprobante


class FakeCertificateParser:
    """Devuelve los datos que se le dieron, o `InvalidCertificate`."""

    def __init__(self, facts=None, *, falla: Exception | None = None) -> None:
        self._facts = facts
        self._falla = falla

    def facts(self, certificate_pem: str):
        if self._falla is not None:
            raise self._falla
        return self._facts


class FakeContingency:
    def __init__(self, activa: bool = False) -> None:
        self.activa = activa

    def active(self) -> bool:
        return self.activa
