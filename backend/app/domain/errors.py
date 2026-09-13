"""
Los «no» del negocio.

Son excepciones propias y no `HTTPException` a propósito: el dominio no sabe
que existe HTTP. Traducirlas a un código de estado es trabajo de la capa de
interfaz, y es lo que permite probar una regla sin levantar un servidor.

Cada una lleva los datos con los que se puede armar un mensaje, y ninguna lleva
la frase: acá solo va lo que pasó. El texto lo escribe la interfaz, que es la
única que sabe en qué idioma está mirando quien lo va a leer (RN-30).

El argumento de `Exception` sí está en español y sí es una oración, pero esa no
la lee ninguna persona: es lo que sale en un traceback. Lo que no puede ser una
frase es cualquier atributo que la interfaz vaya a reenviar —de ahí que
`InvalidBarcode` e `InvalidMovement` lleven un `code`—.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base de todo lo que el negocio rechaza."""


# ------------------------------------------------------------------- valores

class InvalidAmount(DomainError):
    """Un monto que no es un número utilizable."""

    def __init__(self, value: object) -> None:
        super().__init__(f"monto no válido: {value!r}")
        self.value = value


class InvalidQuantity(DomainError):
    """Una cantidad que no tiene sentido: cero, negativa o fraccionaria."""

    def __init__(self, value: object) -> None:
        super().__init__(f"cantidad no válida: {value!r}")
        self.value = value


class InvalidTaxRate(DomainError):
    """Una tasa fuera de 0..1. El 13 % es 0,13, no 13."""

    def __init__(self, value: object) -> None:
        super().__init__(f"tasa de impuesto no válida: {value!r}")
        self.value = value


class UnknownModule(DomainError):
    """Un módulo que no existe (RN-49).

    No es un «no» del negocio sino un error de quien escribe el código: un
    `require_module("purchase")` en singular. Por eso revienta en vez de
    contestar que el plan no lo incluye, que se leería como un problema del
    cliente.
    """

    def __init__(self, module: object) -> None:
        super().__init__(f"módulo desconocido: {module!r}")
        self.module = module


class InvalidBarcode(DomainError):
    """Un código de barras vacío o con caracteres que un lector no produce."""

    def __init__(self, value: object, code: str) -> None:
        super().__init__(f"código de barras no válido ({code}): {value!r}")
        self.value = value
        #: Qué tiene de malo, en código: 'not_text', 'empty', 'too_long',
        #: 'inner_space' o 'control_chars'.
        self.code = code


# ------------------------------------------------------------------- reglas

class InsufficientStock(DomainError):
    """Se pidieron más unidades de las que hay."""

    def __init__(self, product_id: int, available: int, requested: int) -> None:
        super().__init__(
            f"existencias insuficientes del producto {product_id}: "
            f"hay {available} y se piden {requested}"
        )
        self.product_id = product_id
        self.available = available
        self.requested = requested


class InsufficientCash(DomainError):
    """Se quiso sacar de la gaveta más efectivo del que hay."""

    def __init__(self, available: object, requested: object) -> None:
        super().__init__(f"en caja hay {available} y se quieren sacar {requested}")
        self.available = available
        self.requested = requested


class EmptySale(DomainError):
    """Una venta sin líneas no es una venta."""

    def __init__(self) -> None:
        super().__init__("la venta no tiene productos")


class NotSoldInThisSale(DomainError):
    """Se quiso devolver algo que esa venta no llevaba."""

    def __init__(self, product_id: int) -> None:
        super().__init__(f"el producto {product_id} no pertenece a esta venta")
        self.product_id = product_id


class ExcessiveReturn(DomainError):
    """Se quiso devolver más unidades de las que quedan por devolver."""

    def __init__(self, product_id: int, remaining: int, requested: int) -> None:
        super().__init__(
            f"del producto {product_id} quedan {remaining} unidades por devolver "
            f"y se piden {requested}"
        )
        self.product_id = product_id
        self.remaining = remaining
        self.requested = requested


class DuplicateSaleNumber(DomainError):
    """Dos ventas con el mismo número son dos facturas con el mismo
    consecutivo, y eso Hacienda no lo perdona."""

    def __init__(self, sale_number: str) -> None:
        super().__init__(f"ya existe una venta con el número {sale_number}")
        self.sale_number = sale_number


class TotalsMismatch(DomainError):
    """Lo que declaró el POS no es lo que da el servidor al recalcular."""

    def __init__(self, campo: str, declarado: object, calculado: object) -> None:
        super().__init__(
            f"el {campo} declarado ({declarado}) no coincide con el calculado ({calculado})"
        )
        #: 'subtotal', 'tax' o 'total': el nombre del campo en el API. Va hasta
        #: el POS, así que es un nombre y no una palabra de la oración.
        self.campo = campo
        self.declarado = declarado
        self.calculado = calculado


class InsufficientPayment(DomainError):
    """El efectivo recibido no alcanza para el total."""

    def __init__(self, received: object, total: object) -> None:
        super().__init__(f"se recibieron {received} y el total es {total}")
        self.received = received
        self.total = total


class InvalidSource(DomainError):
    """Una entrada de mercadería que no dice de dónde salió."""

    def __init__(self, source: object) -> None:
        super().__init__(f"origen de entrada no válido: {source!r}")
        self.source = source


class DuplicateDocument(DomainError):
    """La misma factura de proveedor, cargada dos veces."""

    def __init__(self, document_number: str) -> None:
        super().__init__(f"el documento {document_number} ya se cargó")
        self.document_number = document_number


class PaymentExceedsBalance(DomainError):
    """Se quiso abonar más de lo que se debe de esa compra (RN-55).

    No se ajusta al saldo en silencio: o es un dedo de más, o el abono va a otra
    factura, y las dos las arregla una persona.
    """

    def __init__(self, balance: str, requested: str) -> None:
        super().__init__(f"el saldo es {balance} y se quieren abonar {requested}")
        self.balance = balance
        self.requested = requested


class InvalidPayment(DomainError):
    """Un abono a proveedor mal formado: monto o método (RN-55, RN-56).

    Con código y no con frase, igual que `InvalidMovement`, y por la misma
    razón: la que no estuviera en la tabla la interfaz la reenviaba tal cual y
    así se colaba el español del dominio hasta la pantalla.

    El método importa más de lo que parece: de los tres, **solo `cash` mueve la
    gaveta**, y uno mal escrito —«efectivo», «CASH»— pasaría de largo por el
    `if` del efectivo, y el turno cerraría con un sobrante igual a lo que se
    pagó. Que el método sea uno de la lista es lo que sostiene RN-56.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        #: Qué está mal: 'amount_not_positive' o 'invalid_method'.
        self.code = code


class BarcodeTaken(DomainError):
    """Se quiso crear un producto con un código que ya existe."""

    def __init__(self, barcode: str) -> None:
        super().__init__(f"ya hay un producto con el código {barcode}")
        self.barcode = barcode


class LineWithoutProduct(DomainError):
    """Una línea que no dice qué producto entra ni cuál crear."""

    def __init__(self, index: int) -> None:
        super().__init__(f"la línea {index} no indica producto")
        self.index = index


class AlreadyCancelled(DomainError):
    def __init__(self, entry_id: int) -> None:
        super().__init__(f"la entrada {entry_id} ya está anulada")
        self.entry_id = entry_id


class CannotCancel(DomainError):
    """Anular dejaría el inventario en negativo: parte ya se vendió."""

    def __init__(self, product_id: int, available: int, added: int) -> None:
        super().__init__(
            f"del producto {product_id} quedan {available} unidades y la entrada agregó {added}"
        )
        self.product_id = product_id
        self.available = available
        self.added = added


class InvalidMovement(DomainError):
    """Un movimiento de caja mal formado: tipo desconocido, monto o motivo."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        #: Qué está mal, en código: 'invalid_type', 'amount_not_positive',
        #: 'missing_reason' u 'opening_negative'. Era una frase en español y la
        #: interfaz la reenviaba tal cual cuando no la reconocía.
        self.code = code


# ------------------------------------------------------------------ catálogo

class CategoryTooDeep(DomainError):
    """Se quiso colgar una categoría de una subcategoría (RN-5)."""

    def __init__(self, parent_id: int) -> None:
        super().__init__(f"la categoría {parent_id} ya es una subcategoría")
        self.parent_id = parent_id


class CategoryHasChildren(DomainError):
    """Se quiso volver hija a una categoría que tiene hijas (RN-5).

    La otra mitad de la regla de profundidad: sin esta, mover una raíz con
    hijas debajo de otra raíz crea un tercer nivel sin crear ninguna fila.
    """

    def __init__(self, category_id: int, children: int) -> None:
        super().__init__(f"la categoría {category_id} tiene {children} subcategorías")
        self.category_id = category_id
        self.children = children


class CategoryIsItsOwnParent(DomainError):
    """Se quiso poner una categoría como madre de sí misma."""

    def __init__(self, category_id: int) -> None:
        super().__init__(f"la categoría {category_id} no puede ser su propia madre")
        self.category_id = category_id


class CategoryInUse(DomainError):
    """Se quiso borrar una categoría con productos o con hijas (RN-7).

    Lleva las dos cuentas porque la frase las nombra y porque quien la lee
    necesita saber qué mover antes de volver a intentarlo.
    """

    def __init__(self, category_id: int, products: int, children: int) -> None:
        super().__init__(
            f"la categoría {category_id} tiene {products} productos "
            f"y {children} subcategorías"
        )
        self.category_id = category_id
        self.products = products
        self.children = children


class CategoryNeedsSubcategory(DomainError):
    """Se quiso colgar un producto de una raíz que ya tiene hijas (RN-6)."""

    def __init__(self, category_id: int, children: int) -> None:
        super().__init__(
            f"la categoría {category_id} tiene {children} subcategorías: "
            "el producto va en una de ellas"
        )
        self.category_id = category_id
        self.children = children
