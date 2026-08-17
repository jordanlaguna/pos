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

from app.domain.money import Money


@dataclass
class FakeProduct:
    id_product: int
    name: str
    price: Money | None
    stock: int


class FakeProductRepository:
    def __init__(self, productos: list[FakeProduct] | None = None) -> None:
        self.productos = {p.id_product: p for p in (productos or [])}
        self.bloqueados: list[list[int]] = []
        # Códigos de barras ya tomados y productos creados por una entrada.
        self.codigos: dict[str, int] = {}
        self.creados: list[tuple] = []
        self._siguiente = max(self.productos, default=0) + 1

    def get(self, product_id: int) -> FakeProduct | None:
        return self.productos.get(product_id)

    def get_by_barcode(self, barcode: str) -> FakeProduct | None:  # pragma: no cover
        return next((p for p in self.productos.values() if p.name == barcode), None)

    def lock_for_sale(self, product_ids: list[int]) -> dict[int, FakeProduct]:
        # Se anota qué se bloqueó y en qué orden: una prueba comprueba que se
        # piden ordenados, que es lo que evita el interbloqueo entre dos cajas.
        self.bloqueados.append(list(product_ids))
        return {i: self.productos[i] for i in product_ids if i in self.productos}

    def adjust_stock(self, product_id: int, delta: int) -> None:
        self.productos[product_id].stock += delta

    def barcode_taken(self, barcode: str) -> bool:
        return barcode in self.codigos

    def create(self, *, name, description, price, barcode, category_id, created_at) -> int:
        nuevo = FakeProduct(self._siguiente, name, price, stock=0)
        self.productos[self._siguiente] = nuevo
        self.codigos[barcode] = self._siguiente
        self.creados.append((name, barcode, price, category_id, created_at))
        self._siguiente += 1
        return nuevo.id_product


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
    total: Money
    created_at: datetime
    lines: list


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


class FakeStockEntryRepository:
    def __init__(self) -> None:
        self.entradas: list[FilaDeEntrada] = []
        self._siguiente = 1

    def get(self, entry_id: int) -> FilaDeEntrada | None:
        return next((e for e in self.entradas if e.id == entry_id), None)

    def applied_with_document(self, document_number: str) -> FilaDeEntrada | None:
        return next(
            (
                e
                for e in self.entradas
                if e.document_number == document_number and e.status == "aplicada"
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


class FakeSettingsRepository:
    """La tasa configurada, sin tabla `settings` de por medio."""

    def __init__(self, rate) -> None:
        self._rate = rate

    def tax_rate(self):
        return self._rate


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
