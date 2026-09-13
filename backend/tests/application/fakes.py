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
    #: Lo que cuesta (RN-54, F10). Cero por omisión: es «no se sabe», que es lo
    #: que tienen los productos de las pruebas anteriores a F10 y lo que hace
    #: que la primera compra establezca el costo.
    cost: Money = field(default_factory=Money.zero)


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

    def update_cost(self, product_id: int, cost: Money) -> None:
        self.productos[product_id].cost = cost

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
    # Lo de F10. Con todo en su valor de reposo esto es una entrada de las de
    # siempre, que es lo que siguen siendo las de las pruebas anteriores.
    supplier_id: int | None = None
    document_key: str | None = None
    document_date: object = None
    payment_terms: str = "cash"
    due_date: object = None
    subtotal: Money | None = None
    tax: Money | None = None


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

    def mark_verified(self, *, environment: str, at: datetime) -> None:
        self._fila(environment).atv_verified_at = at


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
