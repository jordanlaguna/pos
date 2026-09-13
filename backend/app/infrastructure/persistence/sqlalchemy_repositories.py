"""
Repositorios sobre SQLAlchemy.

Traducen entre las filas de la base y los tipos del dominio. Es el único lugar
donde un `Numeric` de MySQL se convierte en `Money` y al revés: adentro no
circula ni un `float`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.domain.cabys import CabysCode
from app.domain.money import Money
from app.domain.tax import TaxRate
from app.models.model_cabys import CabysCache
from app.models.model_cash import CashMovement, CashSession
from app.models.model_product import Product
from app.models.model_return import Return, ReturnDetail
from app.models.model_sale_details import SaleDetail
from app.models.model_sales import Sale
from app.models.model_stock_entry import StockEntry, StockEntryDetail
from app.models.model_supplier import Supplier
from app.utils.tenancy import sucursal_actual, terminal_actual


@dataclass(frozen=True)
class ProductData:
    """Un producto visto desde la aplicación. Cumple `ProductSnapshot`."""

    id_product: int
    name: str
    price: Money | None
    stock: int
    #: `None` es «la tasa configurada del negocio» (RN-9). Lo resuelve el caso de
    #: uso, no este adaptador: acá solo se transporta lo que dice la fila.
    tax_rate: TaxRate | None = None
    #: Lo que cuesta (RN-54). Cero es «no se sabe»: los productos anteriores a
    #: F10 y los que nunca se compraron. La primera compra lo establece.
    cost: Money = Money.zero()


def _a_producto(fila: Product) -> ProductData:
    return ProductData(
        id_product=fila.id_product,
        name=fila.name,
        # `price` puede venir en nulo de una fila vieja; el caso de uso decide
        # qué hacer con eso, acá solo se transporta.
        price=Money(fila.price) if fila.price is not None else None,
        stock=fila.stock,
        tax_rate=TaxRate(fila.tax_rate) if fila.tax_rate is not None else None,
        cost=Money(fila.cost) if fila.cost is not None else Money.zero(),
    )


class SqlAlchemyProductRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, product_id: int) -> ProductData | None:
        fila = self._db.query(Product).filter(Product.id_product == product_id).first()
        return _a_producto(fila) if fila else None

    def get_by_barcode(self, barcode: str) -> ProductData | None:
        fila = self._db.query(Product).filter(Product.barcode == barcode).first()
        return _a_producto(fila) if fila else None

    def lock_for_sale(self, product_ids: list[int]) -> dict[int, ProductData]:
        """
        Trae los productos con `SELECT ... FOR UPDATE`.

        El bloqueo es lo que impide que dos cajas vendan la última unidad a la
        vez: la segunda espera a que la primera termine y entonces ve el stock
        ya descontado. Se piden **ordenados** para que dos transacciones que
        compiten tomen los candados en la misma secuencia; en orden distinto se
        traban una a la otra.
        """
        if not product_ids:
            return {}

        filas = (
            self._db.query(Product)
            .filter(Product.id_product.in_(sorted(set(product_ids))))
            .order_by(Product.id_product)
            .with_for_update()
            .all()
        )
        return {fila.id_product: _a_producto(fila) for fila in filas}

    def adjust_stock(self, product_id: int, delta: int) -> None:
        fila = self._db.query(Product).filter(Product.id_product == product_id).first()
        if fila is not None:
            fila.stock += delta

    def update_cost(self, product_id: int, cost: Money) -> None:
        fila = self._db.query(Product).filter(Product.id_product == product_id).first()
        if fila is not None:
            fila.cost = cost.amount

    def barcode_taken(self, barcode: str) -> bool:
        return (
            self._db.query(Product).filter(Product.barcode == barcode).first() is not None
        )

    def create(
        self,
        *,
        name: str,
        description: str,
        price: Money,
        barcode: str,
        category_id: int,
        created_at: datetime,
    ) -> int:
        fila = Product(
            name=name,
            description=description,
            price=price.amount,
            stock=0,
            barcode=barcode,
            created_at=created_at,
            category_id=category_id,
        )
        self._db.add(fila)
        # flush para tener el id sin cerrar la transacción: si algo falla más
        # adelante, el producto tampoco queda creado.
        self._db.flush()
        return fila.id_product


@dataclass(frozen=True)
class SupplierData:
    """Lo que la aplicación necesita de un proveedor para comprarle."""

    id: int
    name: str
    is_active: bool
    payment_terms_days: int


class SqlAlchemySupplierRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, supplier_id: int) -> SupplierData | None:
        fila = self._db.query(Supplier).filter(Supplier.id == supplier_id).first()
        if fila is None:
            return None
        return SupplierData(
            id=fila.id,
            name=fila.name,
            is_active=bool(fila.is_active),
            payment_terms_days=fila.payment_terms_days or 0,
        )


class SqlAlchemyStockEntryRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, entry_id: int) -> StockEntry | None:
        return self._db.query(StockEntry).filter(StockEntry.id == entry_id).first()

    def applied_with_document(
        self, document_number: str, supplier_id: int | None = None
    ) -> StockEntry | None:
        return (
            self._db.query(StockEntry)
            .filter(
                StockEntry.document_number == document_number,
                StockEntry.status == "aplicada",
                # Por proveedor desde F10: la factura 1234 de un mayorista no es
                # la 1234 de otro. `is_` y no `==` para que el caso sin
                # proveedor compare contra los nulos y no contra nada.
                StockEntry.supplier_id == supplier_id
                if supplier_id is not None
                else StockEntry.supplier_id.is_(None),
            )
            .first()
        )

    def add(
        self,
        *,
        document_number: str | None,
        supplier: str | None,
        source: str,
        user_id: int,
        notes: str | None,
        total_cost: Money,
        created_at: datetime,
        lines: list,
        supplier_id: int | None = None,
        document_key: str | None = None,
        document_date: date | None = None,
        payment_terms: str = "cash",
        due_date: date | None = None,
        subtotal: Money | None = None,
        tax: Money | None = None,
    ) -> int:
        entrada = StockEntry(
            # A qué sucursal entró. Sale del token, no del cuerpo de la
            # petición: si el cliente pudiera decirlo, podría cargarle
            # mercadería a la bodega de otra sucursal (RN-14).
            branch_id=sucursal_actual(),
            document_number=document_number,
            supplier=supplier,
            source=source,
            user_id=user_id,
            created_at=created_at,
            notes=notes,
            status="aplicada",
            total_cost=total_cost.amount,
            supplier_id=supplier_id,
            document_key=document_key,
            document_date=document_date,
            payment_terms=payment_terms,
            due_date=due_date,
            # Sin desglose —una entrada de las de siempre— el subtotal es el
            # total y el impuesto cero: es lo que esa entrada fue.
            subtotal=(subtotal or total_cost).amount,
            tax=(tax or Money.zero()).amount,
        )
        self._db.add(entrada)
        self._db.flush()

        for linea in lines:
            self._db.add(
                StockEntryDetail(
                    entry_id=entrada.id,
                    product_id=linea.product_id,
                    quantity=linea.quantity,
                    unit_cost=linea.unit_cost.amount,
                    subtotal=linea.subtotal.amount,
                    # La tarifa se guarda en porcentaje —13.00 y no 0,13—
                    # porque es como la dice el documento del proveedor y como
                    # la va a leer quien concilie el D-104.
                    tax_rate=linea.tax_rate.as_percent,
                    tax_amount=linea.tax_amount.amount,
                )
            )
        return entrada.id

    def lines_of(self, entry_id: int) -> list:
        return (
            self._db.query(StockEntryDetail)
            .filter(StockEntryDetail.entry_id == entry_id)
            .all()
        )

    def mark_cancelled(self, entry_id: int) -> None:
        entrada = self._db.query(StockEntry).filter(StockEntry.id == entry_id).first()
        entrada.status = "anulada"


class SqlAlchemySaleRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(
        self,
        *,
        sale_number: str,
        client_id: int | None,
        user_id: int,
        subtotal: Money,
        tax: Money,
        total: Money,
        payment_method: str,
        cash_received: Money,
        change_given: Money,
        created_at: datetime,
        lines: list,
    ) -> int:
        venta = Sale(
            # Dónde y en qué caja se cobró. Del token, nunca del cliente: una
            # venta que eligiera su terminal podría cuadrar el arqueo de otra
            # con plata que jamás pasó por esa gaveta (RN-14).
            branch_id=sucursal_actual(),
            terminal_id=terminal_actual(),
            sale_number=sale_number,
            client_id=client_id,
            user_id=user_id,
            subtotal=subtotal.amount,
            tax=tax.amount,
            total=total.amount,
            payment_method=payment_method,
            cash_received=cash_received.amount,
            change_given=change_given.amount,
            created_at=created_at,
        )
        self._db.add(venta)
        # `flush` y no `commit`: asigna el id sin cerrar la transacción, de modo
        # que un fallo posterior revierta también la cabecera. Es la mitad del
        # arreglo del defecto 1.
        self._db.flush()

        for linea in lines:
            self._db.add(
                SaleDetail(
                    sale_id=venta.id,
                    product_id=linea.product_id,
                    quantity=linea.quantity,
                    unit_price=linea.unit_price.amount,
                    subtotal=linea.subtotal.amount,
                    # La tarifa llega **ya resuelta** desde el caso de uso: nunca
                    # nula. Congelarla acá es lo que hace que devolver algo
                    # vendido el mes pasado use la tarifa de entonces y no la de
                    # hoy (RN-12), y lo que permite que una devolución parcial de
                    # una sola tarifa no se calcule con el promedio de la venta.
                    tax_rate=linea.tax_rate.value,
                    tax_amount=linea.tax_rate.apply(linea.subtotal).amount,
                )
            )

        return venta.id

    def get(self, sale_id: int):
        return self._db.query(Sale).filter(Sale.id == sale_id).first()

    def exists_with_number(self, sale_number: str) -> bool:
        return (
            self._db.query(Sale).filter(Sale.sale_number == sale_number).first() is not None
        )

    def sold_quantities(self, sale_id: int) -> dict[int, int]:
        filas = self._db.query(SaleDetail).filter(SaleDetail.sale_id == sale_id).all()
        return {fila.product_id: fila.quantity for fila in filas}

    def sold_prices(self, sale_id: int) -> dict[int, Money]:
        filas = self._db.query(SaleDetail).filter(SaleDetail.sale_id == sale_id).all()
        # `unit_price` de la línea, no el precio de hoy del producto.
        return {fila.product_id: Money(fila.unit_price) for fila in filas}

    def sold_tax_rates(self, sale_id: int) -> dict[int, TaxRate]:
        """La tarifa CONGELADA de cada línea, para las que la tengan.

        Solo las ventas posteriores a la migración 006 la traen; las anteriores
        devuelven un diccionario vacío o incompleto, y el caso de uso cae al
        cociente del encabezado, que para ellas es exacto porque llevan una sola
        tarifa (RN-12).

        Es lo que impide que una devolución parcial de una venta con tarifas
        mezcladas se calcule con el promedio: devolver el medicamento al 2 %
        junto al arroz al 13 % reembolsaría ₡1 075 en vez de ₡1 020.
        """
        filas = self._db.query(SaleDetail).filter(SaleDetail.sale_id == sale_id).all()
        return {
            fila.product_id: TaxRate(fila.tax_rate)
            for fila in filas
            if fila.tax_rate is not None
        }

    def in_window(self, user_id: int, start: datetime, end: datetime) -> list:
        return (
            self._db.query(Sale)
            .filter(Sale.user_id == user_id, Sale.created_at >= start, Sale.created_at <= end)
            .all()
        )


class SqlAlchemyReturnRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def returned_quantities(self, sale_id: int) -> dict[int, int]:
        """Unidades ya devueltas por producto, sumando **todas** las
        devoluciones de esa venta. Es lo que impide devolver dos veces lo
        mismo con dos parciales."""
        filas = (
            self._db.query(ReturnDetail.product_id, ReturnDetail.quantity)
            .join(Return, Return.id == ReturnDetail.return_id)
            .filter(Return.sale_id == sale_id)
            .all()
        )
        totales: dict[int, int] = {}
        for product_id, cantidad in filas:
            totales[product_id] = totales.get(product_id, 0) + cantidad
        return totales

    def add(
        self,
        *,
        sale_id: int,
        user_id: int,
        reason: str,
        subtotal: Money,
        tax: Money,
        total: Money,
        created_at: datetime,
        lines: list,
    ) -> int:
        registro = Return(
            # La devolución se sella donde ocurre, que no tiene por qué ser
            # donde se vendió: se puede devolver en otra sucursal.
            branch_id=sucursal_actual(),
            terminal_id=terminal_actual(),
            sale_id=sale_id,
            user_id=user_id,
            reason=reason,
            # Desde F5 se guarda el desglose y no solo el total: con tarifas
            # mezcladas el impuesto no se puede deducir del total, así que sin
            # estas dos columnas la devolución no tendría con qué cuadrar la caja
            # ni qué reimprimir.
            subtotal=subtotal.amount,
            tax=tax.amount,
            total=total.amount,
            created_at=created_at,
        )
        self._db.add(registro)
        self._db.flush()  # asigna el id sin cerrar la transacción

        for linea in lines:
            self._db.add(
                ReturnDetail(
                    return_id=registro.id,
                    product_id=linea.product_id,
                    quantity=linea.quantity,
                    unit_price=linea.unit_price.amount,
                    subtotal=linea.subtotal.amount,
                    # Copiada de la línea de la venta, no releída del producto:
                    # la del producto pudo cambiar desde entonces (RN-12). Llega
                    # ya resuelta desde el caso de uso.
                    tax_rate=linea.tax_rate.value,
                    tax_amount=linea.tax_rate.apply(linea.subtotal).amount,
                )
            )
        return registro.id

    def total_in_window(self, user_id: int, start: datetime, end: datetime) -> Money:
        total = (
            self._db.query(func.coalesce(func.sum(Return.total), 0))
            .filter(
                Return.user_id == user_id,
                Return.created_at >= start,
                Return.created_at <= end,
            )
            .scalar()
        )
        return Money(total or 0)


class SqlAlchemyCashRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def open_session(self, user_id: int) -> CashSession | None:
        return (
            self._db.query(CashSession)
            .filter(CashSession.user_id == user_id, CashSession.status == "abierta")
            .first()
        )

    def create_session(
        self, *, user_id: int, opening: Money, opened_at: datetime, notes: str | None
    ) -> CashSession:
        sesion = CashSession(
            # Con varias cajas, «el turno de hoy» deja de ser uno solo.
            terminal_id=terminal_actual(),
            user_id=user_id,
            opened_at=opened_at,
            opening_amount=opening.amount,
            status="abierta",
            notes=notes,
        )
        self._db.add(sesion)
        self._db.flush()
        return sesion

    def close_session(
        self, session_id: int, *, counted: Money, closed_at: datetime, notes: str | None
    ) -> CashSession:
        sesion = self._db.query(CashSession).filter(CashSession.id == session_id).first()
        sesion.closing_amount = counted.amount
        sesion.closed_at = closed_at
        sesion.status = "cerrada"
        if notes:
            sesion.notes = notes
        return sesion

    def add_movement(
        self,
        *,
        session_id: int,
        type_: str,
        amount: Money,
        reason: str,
        created_at: datetime,
    ) -> CashMovement:
        movimiento = CashMovement(
            session_id=session_id,
            type=type_,
            amount=amount.amount,
            reason=reason,
            created_at=created_at,
        )
        self._db.add(movimiento)
        self._db.flush()
        return movimiento

    def movements(self, session_id: int) -> list:
        return (
            self._db.query(CashMovement)
            .filter(CashMovement.session_id == session_id)
            .order_by(CashMovement.created_at)
            .all()
        )


class SqlAlchemySettingsRepository:
    """La tasa configurada, leída de la tabla `settings`."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def tax_rate(self) -> TaxRate:
        # `get_tax_rate` ya devuelve la de Costa Rica cuando no hay fila o el
        # valor guardado está fuera de rango: nunca propaga basura a un cálculo
        # de plata.
        from app.services.crud_settings import get_tax_rate

        return TaxRate(get_tax_rate(self._db))


class SqlAlchemyUnitOfWork:
    """
    La transacción de SQLAlchemy, detrás del puerto.

    Al salir por una excepción revierte **siempre**, sea cual sea. El código
    anterior atrapaba solo `SQLAlchemyError`, y por eso un `HTTPException` por
    falta de existencias escapaba sin revertir: ese era el defecto 1.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self.rollback()
        # False: la excepción sigue subiendo. Acá solo se limpia.
        return False

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()


class SqlAlchemyCabysCacheRepository:
    """La caché del catálogo CABYS. Cumple `CabysCacheRepository`.

    **Sin filtro por compañía, y es a propósito**: `cabys_cache` no hereda
    `TenantMixin` porque el catálogo es del país. Es la segunda tabla global del
    sistema, después de `plans`, y no guarda dato de nadie: son códigos que
    Hacienda publica.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    @staticmethod
    def _a_codigo(fila: CabysCache) -> CabysCode:
        return CabysCode(
            code=fila.code,
            description=fila.description,
            tax_rate=TaxRate(fila.tax_rate),
        )

    def search(self, text: str, limit: int) -> list[CabysCode]:
        """Busca en lo que ya se consultó alguna vez.

        Por descripción **y por código**: quien busca sin internet suele estar
        pegando un código que ya usó, y obligarlo a recordar la descripción sería
        una degradación peor que la falta de internet.
        """
        patron = f"%{text}%"
        filas = (
            self._db.query(CabysCache)
            .filter(or_(CabysCache.description.like(patron), CabysCache.code.like(patron)))
            .order_by(CabysCache.description)
            .limit(limit)
            .all()
        )
        return [self._a_codigo(f) for f in filas]

    def by_code(self, code: str) -> CabysCode | None:
        fila = self._db.query(CabysCache).filter(CabysCache.code == code).first()
        return self._a_codigo(fila) if fila else None

    def updated_at(self, code: str) -> datetime | None:
        fila = self._db.query(CabysCache).filter(CabysCache.code == code).first()
        return fila.updated_at if fila else None

    def remember(self, entries: list[CabysCode], now: datetime) -> None:
        """Guarda o actualiza. Es lo que hace que facturar no dependa de que
        Hacienda esté arriba: el código que se le asignó a un producto ya está
        acá el día que no haya internet."""
        for entrada in entries:
            fila = (
                self._db.query(CabysCache)
                .filter(CabysCache.code == entrada.code)
                .first()
            )
            if fila is None:
                self._db.add(
                    CabysCache(
                        code=entrada.code,
                        description=entrada.description,
                        tax_rate=entrada.tax_rate.value,
                        updated_at=now,
                    )
                )
            else:
                # Se refresca lo que puede cambiar: Hacienda corrige
                # descripciones y tarifas, y la caché tiene que seguirlas.
                fila.description = entrada.description
                fila.tax_rate = entrada.tax_rate.value
                fila.updated_at = now
        self._db.commit()
