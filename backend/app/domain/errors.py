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


class InvalidSalePaymentMethod(DomainError):
    """Se quiso cobrar con un método que no está en la lista (T-1104).

    Lleva el valor y no un código, al revés que `InvalidPayment`, porque acá lo
    útil es **cuál** llegó: el caso real no es un método inventado sino uno mal
    escrito —un cliente viejo, una integración— y verlo ahorra el viaje a la base.

    Con texto libre esa venta entraba y quedaba como una fila propia en el
    reporte de métodos de pago, sin sumar al efectivo esperado del arqueo ni ser
    tarjeta. Y desde F11 no se podría asentar: no hay cuenta para «Efectvo».
    """

    def __init__(self, method: str) -> None:
        super().__init__(f"método de pago no admitido: {method!r}")
        self.method = method


class InvalidSaleDocumentType(DomainError):
    """Se pidió un comprobante que el mostrador no emite (RN-85).

    Lleva el valor por lo mismo que `InvalidSalePaymentMethod`: el caso real no
    es un tipo inventado sino un cliente roto, y ver qué mandó ahorra el viaje.
    """

    def __init__(self, document_type: object) -> None:
        super().__init__(f"tipo de comprobante no admitido: {document_type!r}")
        self.document_type = document_type


class InvoiceNeedsReceiver(DomainError):
    """Factura sin cliente (RN-85).

    La factura electrónica exige un receptor con nombre e identificación. Sin
    él, lo que se emite es un tiquete, y emitir una factura sin receptor es un
    rechazo de Hacienda que llega cuando el cliente ya se fue.
    """

    def __init__(self) -> None:
        super().__init__("la factura electrónica necesita un cliente")


class DocumentTypeNotEnabled(DomainError):
    """Se pidió un comprobante que la compañía no emite (RN-88)."""

    def __init__(self, document_type: str) -> None:
        super().__init__(f"la compañía no emite el comprobante {document_type}")
        self.document_type = document_type


class InvoiceNeedsResident(DomainError):
    """Factura a un cliente del extranjero (RN-87, T-727).

    La factura electrónica es para un receptor con cédula costarricense. A quien
    no la tiene se le emite la factura de exportación, o un tiquete, como a
    cualquier cliente.
    """

    def __init__(self) -> None:
        super().__init__("la factura electrónica necesita un receptor del país")


class ExportNeedsReceiver(DomainError):
    """Factura de exportación sin cliente: no hay a quién exportarle (RF-78)."""

    def __init__(self) -> None:
        super().__init__("la factura de exportación necesita un cliente")


class ExportNeedsForeignReceiver(DomainError):
    """Factura de exportación a un cliente del país (RN-87)."""

    def __init__(self) -> None:
        super().__init__("la factura de exportación necesita un cliente del extranjero")


class ExportNeedsForeignAddress(DomainError):
    """El cliente del extranjero no tiene dirección (RF-78).

    La FEE lleva las otras señas extranjeras del receptor en vez de una
    ubicación del país; sin ellas no se emite, y se dice antes de cobrar.
    """

    def __init__(self, client_id: int) -> None:
        super().__init__(f"el cliente {client_id} no tiene dirección extranjera")
        self.client_id = client_id


class ExportLineNeedsTariffHeading(DomainError):
    """Una mercancía de la venta sin partida arancelaria (RF-78).

    Lleva el producto para que la frase pueda nombrarlo: «falta la partida» sin
    decir de cuál obliga a revisar la venta entera.
    """

    def __init__(self, product_id: int) -> None:
        super().__init__(f"el producto {product_id} no tiene partida arancelaria")
        self.product_id = product_id


class ExportTariffNotAllowed(DomainError):
    """Una línea con una tarifa que la factura de exportación no admite (T-720).

    La FEE no tiene balde de no sujeto: una línea con tarifa 01 u 11
    desaparecería del resumen y el total dejaría de cuadrar.
    """

    def __init__(self, product_id: int, tax_code: str) -> None:
        super().__init__(
            f"el producto {product_id} tiene la tarifa {tax_code}, que la exportación no admite"
        )
        self.product_id = product_id
        self.tax_code = tax_code


class InvalidTariffHeading(DomainError):
    """Una partida arancelaria que no son doce dígitos (XSD 4.4)."""

    def __init__(self, value: object) -> None:
        super().__init__(f"partida arancelaria no válida: {value!r}")
        self.value = value


class InvalidForeignAddress(DomainError):
    """Unas señas extranjeras más largas que lo que admite el XML (300)."""

    def __init__(self, length: int, max_length: int) -> None:
        super().__init__(f"la dirección extranjera tiene {length} caracteres y caben {max_length}")
        self.length = length
        self.max_length = max_length


class SupplierNeedsIdentification(DomainError):
    """Una factura de compra a un proveedor sin cédula (T-728).

    El proveedor es el emisor del XML y el emisor lleva identificación: sin
    ella el comprobante nacería para detenerse. Se dice antes de numerar.
    """

    def __init__(self, supplier_id: int) -> None:
        super().__init__(f"el proveedor {supplier_id} no tiene identificación")
        self.supplier_id = supplier_id


class AnnulAfterReturn(DomainError):
    """Anular una venta que ya tiene devoluciones (RN-89).

    Anular es el comprobante entero. Uno a medio devolver ya no se puede anular:
    lo que queda se devuelve.
    """

    def __init__(self, sale_id: int) -> None:
        super().__init__(f"la venta {sale_id} ya tiene devoluciones")
        self.sale_id = sale_id


class AnnulMustBeFull(DomainError):
    """Anular sin devolver todo lo que se vendió (RN-89)."""

    def __init__(self, sale_id: int) -> None:
        super().__init__(f"anular la venta {sale_id} es devolverla entera")
        self.sale_id = sale_id


class NoteNeedsDocument(DomainError):
    """Una nota por monto sobre una venta que no fue comprobante (RN-89).

    Una nota siempre referencia un comprobante emitido: sobre una venta sin tipo
    no hay qué corregir ante Hacienda.
    """

    def __init__(self) -> None:
        super().__init__("la venta no es un comprobante electrónico")


class InvalidNoteType(DomainError):
    """Una nota por monto que no es ND ni NC."""

    def __init__(self, document_type: object) -> None:
        super().__init__(f"{document_type!r} no es una nota")
        self.document_type = document_type


class InvalidNoteReason(DomainError):
    """Un motivo que esa nota no admite en un mostrador de contado (T-726)."""

    def __init__(self, document_type: object, reference_code: object) -> None:
        super().__init__(f"la nota {document_type!r} no admite el motivo {reference_code!r}")
        self.document_type = document_type
        self.reference_code = reference_code


class InvalidNoteAmount(DomainError):
    """El monto de una línea de la nota en cero o negativo."""

    def __init__(self, product_id: int) -> None:
        super().__init__(f"el monto del producto {product_id} tiene que ser positivo")
        self.product_id = product_id


class CreditExceedsLine(DomainError):
    """Una NC por más de lo que queda de la línea (T-726).

    Lo que queda es lo cobrado, más lo que le subieron las ND, menos lo devuelto
    y menos las NC anteriores. Pasarse sería reembolsar plata que el cliente
    nunca pagó.
    """

    def __init__(self, product_id: int, available: object, requested: object) -> None:
        super().__init__(f"al producto {product_id} le quedan {available}, se pidió {requested}")
        self.product_id = product_id
        self.available = available
        self.requested = requested


class ReturnAfterCreditNote(DomainError):
    """Devolver una línea que ya tiene NC por monto (T-726).

    La devolución reembolsa el precio de la línea; sumado a la NC, reembolsaría
    dos veces la misma plata.
    """

    def __init__(self, product_id: int) -> None:
        super().__init__(f"el producto {product_id} ya tiene una nota de crédito por monto")
        self.product_id = product_id


class AnnulAfterNote(DomainError):
    """Anular una venta que ya tiene notas por monto (T-726).

    Anular reembolsa lo cobrado en la venta; con una ND encima no devolvería lo
    que se cobró de más, y con una NC devolvería dos veces.
    """

    def __init__(self, sale_id: int) -> None:
        super().__init__(f"la venta {sale_id} ya tiene notas por monto")
        self.sale_id = sale_id


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


class PurchaseHasPayments(DomainError):
    """Se quiso anular una compra que ya tiene abonos (RN-57).

    Anularla dejaría los abonos colgando de un documento que no existe, y con
    ellos la plata que de verdad salió de la caja o del banco. Lo que hay que
    hacer primero es deshacer los abonos, que es una decisión de quien paga y
    no un efecto secundario de corregir una carga.
    """

    def __init__(self, entry_id: int, payments: int) -> None:
        super().__init__(f"la compra {entry_id} tiene {payments} abono(s)")
        self.entry_id = entry_id
        #: Cuántos. La frase los cuenta, y saber que es uno o siete cambia lo
        #: que la persona tiene que ir a deshacer.
        self.payments = payments


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


# -------------------------------------------------------------- contabilidad

class EntryNotBalanced(DomainError):
    """Un asiento cuyos débitos no igualan a sus créditos (RN-58).

    No es un asiento con un error: **no es un asiento**. Por eso lo levanta el
    constructor y no una comprobación aparte que alguien pueda olvidar llamar.

    Que llegue hasta una respuesta HTTP significa que un asiento automático se
    armó mal, y eso es un defecto del programa, no del usuario. Tiene código
    igual —y viaja con las dos sumas— porque un asiento **manual** sí lo puede
    provocar escribiendo, y ahí quien lo escribió necesita ver por cuánto.
    """

    def __init__(self, debits: str, credits: str) -> None:
        super().__init__(f"el asiento no balancea: {debits} contra {credits}")
        self.debits = debits
        self.credits = credits


class InvalidJournalLine(DomainError):
    """Una línea de asiento que no es ni un débito ni un crédito.

    Con código y no con frase, como `InvalidMovement` y `InvalidPayment`.

    La regla de las dos columnas —una de las dos es cero— se vigila acá y no con
    un CHECK en la base (plan §5): así se escribe una vez, con su prueba, y vale
    igual para el asiento automático y para el que alguien teclea.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        #: Qué está mal: 'both_sides', 'negative' o 'empty'.
        self.code = code


class AccountIsSystem(DomainError):
    """Se quiso borrar o desactivar una cuenta que el mapeo necesita (RN-64).

    No es una preferencia de orden: sin esa cuenta, el papel que la usaba se
    queda sin dónde caer y su saldo se va a «por clasificar» sin que nadie lo
    haya decidido. El contador la puede **renombrar** —eso sí— porque el mapeo
    apunta al id y no al nombre.
    """

    def __init__(self, code: str) -> None:
        super().__init__(f"la cuenta {code} es de sistema")
        self.code = code


class AccountInUse(DomainError):
    """Se quiso borrar una cuenta con movimientos (RN-64).

    Borrarla se llevaría su historia: los asientos que la nombran dejarían de
    poder decir contra qué se hicieron. Lo que sí se puede es **desactivarla**,
    que la saca de las listas donde se escoge y deja el libro intacto.
    """

    def __init__(self, code: str, lines: int) -> None:
        super().__init__(f"la cuenta {code} tiene {lines} línea(s) de asiento")
        self.code = code
        self.lines = lines


class NothingToReclassify(DomainError):
    """Se quiso reclasificar un asiento que no tiene nada en «por clasificar».

    Pasa de verdad cuando dos personas miran la misma pantalla y una reclasifica
    primero. No es un error del que llega segundo: es que ya está resuelto.
    """

    def __init__(self, entry_id: int) -> None:
        super().__init__(f"el asiento {entry_id} no tiene nada por clasificar")
        self.entry_id = entry_id


class PeriodNotCloseable(DomainError):
    """Se quiso cerrar un mes con el anterior todavía abierto (RF-52).

    El orden importa porque el saldo de un mes arranca donde terminó el
    anterior. Cerrar noviembre con octubre abierto congelaría un balance que
    todavía puede cambiar por debajo, y el balance ya entregado dejaría de
    coincidir con el libro sin que nadie tocara noviembre.
    """

    def __init__(self, year: int, month: int, *, blocking_year: int, blocking_month: int) -> None:
        super().__init__(
            f"no se puede cerrar {year}-{month:02d}: "
            f"{blocking_year}-{blocking_month:02d} sigue abierto"
        )
        self.year = year
        self.month = month
        self.blocking_year = blocking_year
        self.blocking_month = blocking_month


class PeriodClosed(DomainError):
    """Se quiso escribir con fecha dentro de un periodo cerrado (RN-61).

    Cerrado es inmutable, y no se reabre: reabrir es la puerta por donde un
    balance ya entregado deja de coincidir con el libro. Lo que haya que
    corregir se corrige con un asiento de ajuste en el periodo abierto.
    """

    def __init__(self, year: int, month: int) -> None:
        super().__init__(f"el periodo {year}-{month:02d} está cerrado")
        self.year = year
        self.month = month


# ------------------------------------------------------- factura electrónica

class InvalidEnvironment(DomainError):
    """Un ambiente que no es ni `sandbox` ni `production`.

    No es un dato que escriba una persona —sale de una lista cerrada— así que
    llegar acá significa que algo lo compuso mal. Se rechaza igual: el ambiente
    decide contra qué IdP se transmite y con qué llave se firma, y equivocarse
    en él es emitir con efecto fiscal lo que iba a ser un ensayo.
    """

    def __init__(self, value: object) -> None:
        super().__init__(f"ambiente no válido: {value!r}")
        self.value = value


class InvalidDocumentKind(DomainError):
    """Una clase de documento que el almacén no sabe guardar (plan §7.3)."""

    def __init__(self, value: object) -> None:
        super().__init__(f"clase de documento no válida: {value!r}")
        self.value = value


class InvalidClave(DomainError):
    """Una clave numérica con la que no se puede armar una ruta.

    Se comprueba el largo, que sean dígitos y que el día y el mes existan —que
    es lo que arma la carpeta—, no que la clave sea correcta: el país y el
    código de seguridad son problema de quien la emitió, y rechazarlos acá
    dejaría comprobantes legítimos sin poder archivarse.
    """

    def __init__(self, value: object, code: str) -> None:
        super().__init__(f"clave numérica no válida ({code}): {value!r}")
        self.value = value
        self.code = code


class IdentificationTypeRequired(DomainError):
    """Un cliente sin tipo de identificación y con una cédula que no lo deja ver.

    El tipo va en el receptor del comprobante y se imprime («Cédula física»).
    Cuando no se eligió, se deduce por la longitud; cuando tampoco así se sabe,
    hay que preguntar: adivinar sería emitir un receptor que Hacienda rechaza
    (T-617).
    """

    def __init__(self) -> None:
        super().__init__("falta el tipo de identificación")


class InvalidIdentificationType(DomainError):
    """Un tipo de identificación que no es ninguno de los seis de Hacienda.

    Sale de una lista cerrada, así que llegar acá con un valor raro significa
    que alguien mandó el campo a mano. Se rechaza porque el tipo viaja dentro
    del XML: uno inventado no lo rechaza el sistema, lo rechaza Hacienda.
    """

    def __init__(self, value: object) -> None:
        super().__init__(f"tipo de identificación no válido: {value!r}")
        self.value = value


class InvalidSigningKey(DomainError):
    """No se pudo armar el nombre de la llave de firma.

    El nombre se deriva de la compañía y el ambiente, y los dos los pone el
    servidor: si acá llega algo que no es una compañía, lo que hay es un error
    de programación. Se rechaza en vez de componer un nombre cualquiera, porque
    un nombre cualquiera es una llave de otro.
    """

    def __init__(self, company_id: object) -> None:
        super().__init__(f"compañía no válida para una llave de firma: {company_id!r}")
        self.company_id = company_id


class InvalidOfficeCode(DomainError):
    """Un código de sucursal o de terminal que Hacienda no aceptaría (RN-15).

    Los dos van **dentro de la clave de 50 dígitos** del comprobante, con tres y
    cinco dígitos exactos. Un código mal formado no lo descubre el sistema: lo
    descubre Hacienda al rechazar la factura, con el cliente esperando.

    Lleva `code` por lo mismo que `InvalidBarcode`: 'not_text', 'empty',
    'not_digits' o 'too_long'. Lo que hay que hacer es distinto en cada uno
    —«escriba un número» no es «ese número no cabe»— y la frase la arma el POS.
    """

    def __init__(self, value: object, code: str, digits: int) -> None:
        super().__init__(f"código de {digits} dígitos no válido ({code}): {value!r}")
        self.value = value
        self.code = code
        #: Cuántos dígitos pedía. Va en el «no» porque es lo único que le dice a
        #: quien escribió de más cuánto le sobra.
        self.digits = digits


class InvalidLocation(DomainError):
    """Una ubicación del emisor que Hacienda no aceptaría (T-722, RN-83).

    `field` dice cuál de los cinco campos —`province`, `canton`, `district`,
    `neighborhood` u `other_signs`— y `reason` qué le pasa: `required`,
    `unknown` (un código que no está en la nota 14, o que no es de la provincia
    o del cantón elegidos), `too_short` o `too_long`. Lo que hay que hacer es
    distinto en cada uno, y la frase la arma el POS.
    """

    def __init__(self, field: str, reason: str, value: object = None) -> None:
        super().__init__(f"ubicación no válida: {field} ({reason}) {value!r}")
        self.field = field
        self.reason = reason
        self.value = value


class EInvoicingNeedsIssuer(DomainError):
    """Se quiso encender la factura electrónica sin lo que el emisor necesita.

    Sin identificación no hay clave, y sin ubicación ni correo el XML no valida
    (RN-83): encenderla así sería vender comprobantes que no se pueden emitir.
    `missing` es la lista de lo que falta, en orden: `identification`, `email`,
    `location`.
    """

    def __init__(self, missing: tuple[str, ...]) -> None:
        super().__init__(f"faltan datos del emisor: {', '.join(missing)}")
        self.missing = missing


class InvalidKeyPart(DomainError):
    """Una pieza del consecutivo o de la clave que no cabe donde va (T-704, T-705).

    `part` es cuál —`sequence`, `document_type`, `issuer`, `consecutive`,
    `situation`, `security_code`— y `value` lo que llegó. Todas las pone el
    sistema, así que esto es un error de programación o un dato de la compañía
    mal cargado, nunca algo que escribió el cajero.
    """

    def __init__(self, part: str, value: object) -> None:
        super().__init__(f"pieza de la clave no válida: {part} = {value!r}")
        self.part = part
        self.value = value


class InvalidSequenceStart(DomainError):
    """El último consecutivo que se indica no es uno (T-616): no es un entero, es
    negativo o no cabe en los diez dígitos de la clave."""

    def __init__(self, value: object) -> None:
        super().__init__(f"último consecutivo no válido: {value!r}")
        self.value = value


class SequenceCannotGoDown(DomainError):
    """El arranque de una serie solo sube (RN-38): bajarlo es volver a emitir
    números que ya se usaron, y eso es rechazo seguro."""

    def __init__(self, current: int, requested: int) -> None:
        super().__init__(f"la serie va en {current} y se pidió {requested}")
        self.current = current
        self.requested = requested


class SequenceInUse(DomainError):
    """La serie ya emitió con este sistema (RN-38): desde ahí el contador es
    suyo y no se mueve a mano."""

    def __init__(self, document_type: str) -> None:
        super().__init__(f"la serie {document_type} ya emitió con este sistema")
        self.document_type = document_type


class IssuerIdentificationRequired(DomainError):
    """La compañía emite comprobantes y no tiene identificación (RN-45).

    La clave lleva la cédula del emisor en las posiciones 10 a 21, así que sin
    ella no hay comprobante. La identificación la fija soporte en `companies`,
    no el negocio en su configuración: es la del certificado.

    Lleva `reason`: `missing` si no hay, `invalid` si la que hay no cabe en la
    clave —letras, o más de doce dígitos—. En los dos casos lo arregla soporte.
    """

    def __init__(self, reason: str = "missing") -> None:
        super().__init__(f"la compañía no tiene una identificación de emisor válida ({reason})")
        self.reason = reason


# ------------------------------------------------------------------ planilla


class InvalidSchedule(DomainError):
    """Una jornada que no se puede correr (RN-94, T-1202).

    `field` dice cuál de sus datos —`frequency`, `shift`, `hours_per_day`,
    `workdays_per_week`, `first_cut_day`, `cut_weekday` o `series_start`— y
    `reason` qué le pasa: `unknown` (un valor que no está en la lista),
    `required` (la periodicidad lo pide y no vino), `unexpected` (lo pide otra
    periodicidad) o `out_of_range`.
    """

    def __init__(self, field: str, reason: str, value: object = None) -> None:
        super().__init__(f"jornada no válida: {field} ({reason}) {value!r}")
        self.field = field
        self.reason = reason
        self.value = value


class InvalidCutDate(DomainError):
    """Una fecha que no es corte de la jornada (RN-94).

    Una quincenal que corta el 15 no tiene corte el 20. El periodo sale del
    corte, así que un corte inventado inventaría también el periodo.
    """

    def __init__(self, cut: object, frequency: str) -> None:
        super().__init__(f"{cut!r} no es fecha de corte de una jornada {frequency}")
        self.cut = cut
        self.frequency = frequency


class RatesMissing(DomainError):
    """A la fecha de corte falta una tasa que la planilla necesita (RN-67).

    `missing` son los pares `concepto:pagador` que faltan, ordenados. Calcular
    sin ellos daría una planilla que parece bien y cobra de menos: sin la fila
    del IVM, la boleta saldría sin IVM y nadie lo notaría hasta la CCSS.
    """

    def __init__(self, missing: tuple[str, ...], on: object) -> None:
        super().__init__(f"faltan tasas al {on}: {', '.join(missing)}")
        self.missing = missing
        self.on = on


class InvalidAction(DomainError):
    """Una acción de personal a la que le falta o le sobra algo (RN-90).

    `field` es el dato —`kind`, `ends_on`, `hours`, `days`, `amount`,
    `total_amount`, `new_salary`, `position_id` o `is_recurring`— y `reason`,
    `unknown`, `required`, `not_positive`, `before_start`, `single_day`,
    `too_many` o `not_allowed`. Cada tipo pide lo suyo: unas horas extra sin
    horas no son nada, y un aumento con fecha final no existe.
    """

    def __init__(self, field: str, reason: str, value: object = None) -> None:
        super().__init__(f"acción no válida: {field} ({reason}) {value!r}")
        self.field = field
        self.reason = reason
        self.value = value


class InvalidPayrollRate(DomainError):
    """Una tasa que no se puede sembrar (RN-67).

    `field` es `payer` o `value`, y `reason`, `unknown` o `out_of_range`: una
    carga de la CCSS es una fracción entre cero y uno —el 5,5 % es 0,055, no
    5,5—; una regla puede ser un número de días o un monto, pero no negativo.
    """

    def __init__(self, field: str, reason: str, value: object = None) -> None:
        super().__init__(f"tasa de planilla no válida: {field} ({reason}) {value!r}")
        self.field = field
        self.reason = reason
        self.value = value


class RateNotNewer(DomainError):
    """Una tasa nueva que no es posterior a la última del mismo concepto.

    Una tasa no se edita: se agrega otra con su vigencia (RN-67). Aceptar una con
    fecha igual o anterior a la última sería reescribir el pasado de corridas
    que ya se calcularon con la otra.
    """

    def __init__(self, concept: str, payer: str, latest: object) -> None:
        super().__init__(f"{concept}:{payer} ya tiene una tasa desde {latest}")
        self.concept = concept
        self.payer = payer
        self.latest = latest


class InvalidEmployee(DomainError):
    """Un empleado al que le falta o le sobra algo (RN-72, T-1205).

    `field` es el dato —`identification_type`, `identification`, `first_name`,
    `last_name_1`, `birth_date`, `gender`, `marital_status`, `nationality`,
    `email`, `iban`, `dependent_children`, `terminated_on` o
    `termination_cause`— y `reason`, `unknown`, `required`, `not_digits`,
    `bad_format`, `too_long`, `too_young`, `in_the_future`, `negative` o
    `before_hire`. Son los datos que piden los archivos de la CCSS y del INS:
    un dato mal escrito acá es un archivo rechazado dentro de un mes.
    """

    def __init__(self, field: str, reason: str, value: object = None) -> None:
        super().__init__(f"empleado no válido: {field} ({reason}) {value!r}")
        self.field = field
        self.reason = reason
        self.value = value


class InvalidContract(DomainError):
    """Un contrato que no se puede abrir (RN-94, T-1205).

    `field` es `period_salary`, `valid_from`, `solidarista_rate`,
    `schedule_id` o `position_id`, y `reason`, `not_positive`, `before_hire`,
    `overlaps`, `out_of_range` o `inactive`. Un contrato nuevo empieza después
    del anterior: dos vigentes a la vez pagarían dos salarios.
    """

    def __init__(self, field: str, reason: str, value: object = None) -> None:
        super().__init__(f"contrato no válido: {field} ({reason}) {value!r}")
        self.field = field
        self.reason = reason
        self.value = value


class InvalidPayrollSettings(DomainError):
    """Un dato de la configuración de planilla que no sirve (RF-56, T-1217).

    `field` es `employer_number`, `name`, `ccss_code`, `ins_code`, `number` o
    `rt_rate`, y `reason`, `required`, `bad_format`, `too_short`, `too_long` u
    `out_of_range`. El número patronal y los códigos de ocupación van tal cual
    en los archivos de la CCSS y del INS, así que se revisan al escribirlos y
    no al exportar.
    """

    def __init__(self, field: str, reason: str, value: object = None) -> None:
        super().__init__(f"configuración de planilla no válida: {field} ({reason}) {value!r}")
        self.field = field
        self.reason = reason
        self.value = value


class ExportDataIncomplete(DomainError):
    """Falta un dato para armar el archivo de la CCSS o del INS (RN-96, T-1211).

    `missing` son pares `(employee_id, campos)` y `company`, los campos de la
    compañía que faltan —el número patronal, la póliza—. Se dice antes de
    exportar y no se exporta a medias: un archivo con un trabajador menos es un
    trabajador sin seguro ese mes.
    """

    def __init__(self, missing: tuple[tuple[int, tuple[str, ...]], ...], company: tuple[str, ...]) -> None:
        super().__init__(f"faltan datos para exportar: {missing} {company}")
        self.missing = missing
        self.company = company


class InvalidTaxBrackets(DomainError):
    """Un juego de tramos de renta que no se puede sembrar (RN-73, T-1221).

    `reason` es `empty`, `not_from_zero`, `gap`, `empty_range`,
    `open_end_not_last`, `no_open_end`, `rate_out_of_range` o
    `credit_negative`, e `index` el tramo donde se vio. Un juego con un hueco
    deja un salario sin tramo, y ese salario no paga renta sin que nadie lo
    note.
    """

    def __init__(self, reason: str, index: int | None = None) -> None:
        super().__init__(f"tramos de renta no válidos: {reason} (tramo {index})")
        self.reason = reason
        self.index = index


# ------------------------------------------------------- la transmisión (F7)


class UnknownDocument(DomainError):
    """No hay comprobante con ese id en esta compañía."""

    def __init__(self, document_id: int) -> None:
        super().__init__(document_id)
        self.document_id = document_id


class DocumentNotStopped(DomainError):
    """Se pidió reintentar a mano algo que no está detenido (RF-36).

    Lo que está en cola ya se va a intentar solo, y lo aceptado o rechazado no
    se vuelve a mandar: un rechazo se corrige con otro comprobante.
    """

    def __init__(self, document_id: int, status: str) -> None:
        super().__init__(document_id, status)
        self.document_id = document_id
        self.status = status


class ProductionGateLocked(DomainError):
    """Falta ver aceptados en pruebas los comprobantes que Hacienda exige
    antes de producción (RN-46, T-713). `missing` dice cuáles."""

    def __init__(self, missing: tuple[str, ...]) -> None:
        super().__init__(missing)
        self.missing = missing
