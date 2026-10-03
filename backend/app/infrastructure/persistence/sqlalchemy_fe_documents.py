"""
`fe_documents` como recorrido, y el comprobante armado desde su origen (F7).

Dos adaptadores, los dos de SQLAlchemy:

* `SqlAlchemyTransmissionRepository` cumple `TransmissionRepository`: lo que la
  cola escribe en cada paso y lo que la pantalla lee.
* `SqlAlchemyComprobanteSource` cumple `ComprobanteSource`: lee la venta, la
  devolución o la nota con su emisor y su receptor y arma el `Comprobante` que
  `fe_xml.construir` convierte en XML. **Acá no hay regla fiscal**: qué código
  de tarifa, qué medio de pago, cuánto IVA se devuelve, lo dicen los módulos de
  dominio; esto solo lee filas y las acomoda.

Como el resto de los repositorios, hablan de la compañía del contexto. El
trabajador de la cola abre un `with compania(cid)` por compañía (T-708).
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.application.ports.fe_documents import (
    DocumentEvent,
    DocumentSnapshot,
    DocumentUpdate,
    QueueCounts,
    TransmissionHealth,
)
from app.application.use_cases.number_document import SOURCE_NOTE, SOURCE_PURCHASE, SOURCE_RETURN, SOURCE_SALE
from app.domain import fe_transmission as recorrido
from app.domain.fe_exemptions import Exemption
from app.domain.fe_issuer import is_valid_email
from app.domain.fe_notes import REFERS_TO_OTHER
from app.domain.fe_payment_methods import CASH, code_for, code_for_purchase
from app.domain.fe_tax_codes import purchase_line_code, rate_for, suggested_code
from app.domain.purchases import credit_term_days
from app.domain.fe_vat_refund import Payment, TaxedLine, vat_refund
from app.domain.fe_xml import (
    Comprobante,
    ComprobanteInvalido,
    Exoneracion,
    Identificacion,
    Impuesto,
    Linea,
    MedioPago,
    Parte,
    Referencia,
    Ubicacion,
)
from app.domain.fe_document_type import EXPORT_INVOICE
from app.domain.hacienda import identification_type_for
from app.domain.locations import location_from_settings
from app.domain.tax import TaxRate
from app.models.model_client import Client
from app.models.model_company import Company
from app.models.model_fe import FeDocument, FeDocumentEvent
from app.models.model_note import SaleNote, SaleNoteLine
from app.models.model_product import Product
from app.models.model_return import Return, ReturnDetail
from app.models.model_sale_details import SaleDetail
from app.models.model_sales import Sale
from app.models.model_stock_entry import StockEntry, StockEntryDetail
from app.models.model_supplier import Supplier, SupplierPayment
from app.utils.tenancy import compania_actual

# --------------------------------------------------------------- el recorrido


def _snapshot(fila: FeDocument) -> DocumentSnapshot:
    return DocumentSnapshot(
        id=fila.id,
        company_id=fila.company_id,
        source_type=fila.source_type,
        source_id=fila.source_id,
        document_type=fila.document_type,
        environment=fila.environment,
        clave=fila.clave,
        consecutive=fila.consecutive,
        situation=fila.situation,
        issued_at=fila.issued_at,
        status=fila.status or recorrido.NUMBERED,
        economic_activity=fila.economic_activity,
        failures=fila.failures or 0,
        polls=fila.polls or 0,
        first_failure_at=fila.first_failure_at,
        last_attempt_at=fila.last_attempt_at,
        unreachable_at=fila.unreachable_at,
        next_attempt_at=fila.next_attempt_at,
        signed_at=fila.signed_at,
        sent_at=fila.sent_at,
        resolved_at=fila.resolved_at,
        stop_reason=fila.stop_reason,
        stop_detail=fila.stop_detail,
        hacienda_status=fila.hacienda_status,
        xml_key=fila.xml_key,
        response_key=fila.response_key,
    )


class SqlAlchemyTransmissionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _fila(self, document_id: int) -> FeDocument | None:
        return self._db.query(FeDocument).filter(FeDocument.id == document_id).first()

    def get(self, document_id: int) -> DocumentSnapshot | None:
        fila = self._fila(document_id)
        return _snapshot(fila) if fila is not None else None

    def latest_for(self, source_type: str, source_id: int) -> DocumentSnapshot | None:
        fila = (
            self._db.query(FeDocument)
            .filter(FeDocument.source_type == source_type, FeDocument.source_id == source_id)
            .order_by(FeDocument.id.desc())
            .first()
        )
        return _snapshot(fila) if fila is not None else None

    def due(self, now: datetime, *, limit: int) -> list[DocumentSnapshot]:
        filas = (
            self._db.query(FeDocument)
            .filter(
                FeDocument.status.in_(recorrido.PENDING),
                FeDocument.next_attempt_at.isnot(None),
                FeDocument.next_attempt_at <= now,
            )
            .order_by(FeDocument.next_attempt_at, FeDocument.id)
            .limit(limit)
            .all()
        )
        return [_snapshot(f) for f in filas]

    def update(self, document_id: int, change: DocumentUpdate) -> DocumentSnapshot:
        fila = self._fila(document_id)
        if fila is None:
            raise LookupError(document_id)
        for campo, valor in change.fields().items():
            setattr(fila, campo, valor)
        self._db.flush()
        return _snapshot(fila)

    def add_event(self, document_id: int, event: DocumentEvent) -> None:
        self._db.add(
            FeDocumentEvent(
                company_id=compania_actual(),
                document_id=document_id,
                at=event.at,
                event=event.event,
                detail=(event.detail or None),
            )
        )
        self._db.flush()

    def events(self, document_id: int) -> list[DocumentEvent]:
        filas = (
            self._db.query(FeDocumentEvent)
            .filter(FeDocumentEvent.document_id == document_id)
            .order_by(FeDocumentEvent.id)
            .all()
        )
        return [DocumentEvent(at=f.at, event=f.event, detail=f.detail or "") for f in filas]

    def health(self) -> TransmissionHealth:
        # Solo cuando el que no contestó fue Hacienda o su IdP (RN-43). Antes era
        # cualquier `retrying`, y Vault sellado tras reiniciar la máquina ponía
        # a todo el negocio a emitir en una situación que Hacienda rechaza.
        ultima_falla = self._db.query(func.max(FeDocument.unreachable_at)).scalar()
        # Un contacto bueno con Hacienda es un envío que recibió el 202, un
        # veredicto, o una consulta que contestó aunque fuera «procesando».
        candidatos = [
            self._db.query(func.max(FeDocument.sent_at)).scalar(),
            self._db.query(func.max(FeDocument.resolved_at)).scalar(),
            self._db.query(func.max(FeDocument.last_attempt_at))
            .filter(FeDocument.status == recorrido.SENT, FeDocument.failures == 0)
            .scalar(),
        ]
        exitos = [c for c in candidatos if c is not None]
        return TransmissionHealth(
            last_transient_failure_at=ultima_falla,
            last_success_at=max(exitos) if exitos else None,
        )

    def stopped(self) -> list[DocumentSnapshot]:
        filas = (
            self._db.query(FeDocument)
            .filter(FeDocument.status == recorrido.STOPPED)
            .order_by(FeDocument.issued_at, FeDocument.id)
            .all()
        )
        return [_snapshot(f) for f in filas]

    def counts(self) -> QueueCounts:
        por_estado = {
            estado: int(cuantos)
            for estado, cuantos in self._db.query(FeDocument.status, func.count(FeDocument.id))
            .group_by(FeDocument.status)
            .all()
        }
        mas_viejo = (
            self._db.query(func.min(FeDocument.issued_at))
            .filter(FeDocument.status.in_(recorrido.PENDING))
            .scalar()
        )
        return QueueCounts(by_status=por_estado, oldest_pending_at=mas_viejo)

    def accepted_by_type(self, environment: str) -> dict[str, int]:
        return {
            tipo: int(cuantos)
            for tipo, cuantos in self._db.query(
                FeDocument.document_type, func.count(FeDocument.id)
            )
            .filter(FeDocument.status == recorrido.ACCEPTED, FeDocument.environment == environment)
            .group_by(FeDocument.document_type)
            .all()
        }


# ------------------------------------------------------------- el comprobante

#: Lo que lleva una línea cuando el producto no dijo su unidad. «Unid» es el
#: código de la nota 11 del anexo para «unidad».
UNIDAD_POR_OMISION = "Unid"

#: La condición de venta del POS: contado. Vender a crédito es otra fase (T-729).
CONTADO = "01"
#: La condición de venta a crédito, con su plazo en días (nota 5 del anexo).
CREDITO = "02"
#: El tipo de documento de referencia de una factura de compra: el comprobante
#: de respaldo que aporta el proveedor (nota 10, código 14), como en la FEC
#: aceptada de `docs/`.
REFERENCIA_RESPALDO = "14"

#: Hacienda escribe la hora con su desfase. Costa Rica no cambia de hora.
_DESFASE = "-06:00"


def _digitos(valor: object) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def _fecha(momento: datetime) -> str:
    return f"{momento:%Y-%m-%dT%H:%M:%S}{_DESFASE}"


def _decimal(valor: object) -> Decimal:
    return valor if isinstance(valor, Decimal) else Decimal(str(valor or 0))


class SqlAlchemyComprobanteSource:
    """Arma el `Comprobante` de una venta, una devolución o una nota.

    `proveedor_sistemas` es la cédula de quien hace el software; sin ella va la
    del propio emisor, que es lo que traen los comprobantes aceptados de
    `docs/hacienda/costa-rica/XML-Ejemplos/`.
    """

    def __init__(self, db: Session, *, proveedor_sistemas: str | None = None) -> None:
        self._db = db
        self._proveedor = (proveedor_sistemas or "").strip() or None

    # ------------------------------------------------------------ entrada

    def comprobante(self, document: DocumentSnapshot) -> Comprobante:
        emisor, actividad = self._emisor()
        actividad = document.economic_activity or actividad
        if document.source_type == SOURCE_SALE:
            return self._de_venta(document, emisor, actividad)
        if document.source_type == SOURCE_RETURN:
            return self._de_devolucion(document, emisor, actividad)
        if document.source_type == SOURCE_NOTE:
            return self._de_nota(document, emisor, actividad)
        if document.source_type == SOURCE_PURCHASE:
            return self._de_compra(document, emisor, actividad)
        raise ComprobanteInvalido("origen_desconocido", document.source_type)

    # ------------------------------------------------------------ emisor

    def _emisor(self) -> tuple[Parte, str]:
        from app.services.crud_settings import get_economic_activity, get_settings

        company = self._db.get(Company, compania_actual())
        if company is None or not _digitos(company.identificacion):
            raise ComprobanteInvalido("emisor_sin_identificacion")
        datos = get_settings(self._db)["data"] or {}
        negocio = datos.get("business") if isinstance(datos.get("business"), dict) else {}
        negocio = negocio or (datos.get("negocio") if isinstance(datos.get("negocio"), dict) else {}) or {}

        nombre = str(negocio.get("legalName") or negocio.get("name") or company.nombre or "").strip()
        comercial = str(negocio.get("name") or "").strip()
        ubicacion = location_from_settings(negocio.get("location"))
        tipo = company.identification_type or identification_type_for(company.identificacion or "")
        if not tipo:
            raise ComprobanteInvalido("emisor_sin_tipo_de_identificacion")
        emisor = Parte(
            nombre=nombre[:100],
            identificacion=Identificacion(tipo=tipo, numero=_digitos(company.identificacion)),
            ubicacion=Ubicacion(
                provincia=ubicacion.province,
                canton=ubicacion.canton,
                distrito=ubicacion.district,
                otras_senas=ubicacion.other_signs,
                barrio=ubicacion.neighborhood,
            ),
            nombre_comercial=comercial[:80] if comercial and comercial != nombre else "",
            telefono=_digitos(negocio.get("phone"))[:20],
            correo=str(negocio.get("email") or "").strip(),
        )
        return emisor, get_economic_activity(self._db) or ""

    # ---------------------------------------------------------- receptor

    def _receptor(
        self, client_id: int | None, *, export: bool = False
    ) -> tuple[Parte | None, Exoneracion | None]:
        if client_id is None:
            return None, None
        cliente = self._db.query(Client).filter(Client.id_client == client_id).first()
        if cliente is None:
            raise ComprobanteInvalido("receptor_desconocido", client_id)
        tipo = cliente.identification_type or identification_type_for(cliente.identification or "")
        if not tipo:
            raise ComprobanteInvalido("receptor_sin_tipo_de_identificacion")
        nombre = " ".join(
            p for p in (cliente.name, cliente.last_name, cliente.second_name) if p and str(p).strip()
        ).strip()
        correo = str(cliente.email or "").strip()
        if export:
            # El receptor de una exportación (T-727): identificación tal como se
            # escribió —un pasaporte no son dígitos—, sin ubicación y con sus
            # señas extranjeras en su lugar. Sin exoneración: el perfil 09 no la
            # admite. Que sea un `05` y que traiga señas lo exige el armador.
            numero = str(cliente.identification or "").strip()[:20]
            return (
                Parte(
                    nombre=nombre[:100] or numero,
                    identificacion=Identificacion(tipo=tipo, numero=numero),
                    otras_senas_extranjero=str(cliente.foreign_address or "").strip(),
                    correo=correo if is_valid_email(correo) else "",
                ),
                None,
            )
        receptor = Parte(
            nombre=nombre[:100] or _digitos(cliente.identification),
            identificacion=Identificacion(tipo=tipo, numero=_digitos(cliente.identification)),
            correo=correo if is_valid_email(correo) else "",
        )
        return receptor, self._exoneracion(cliente)

    @staticmethod
    def _exoneracion(cliente: Client) -> Exoneracion | None:
        if not cliente.exo_document_type:
            return None
        # `Exemption` comprueba que esté entera; lo que falte es un
        # `InvalidExemption`, que detiene el documento diciendo qué.
        exencion = Exemption(
            document_type=str(cliente.exo_document_type),
            document_number=str(cliente.exo_document_number or ""),
            institution=str(cliente.exo_institution or ""),
            date=str(cliente.exo_date or ""),
            points=_decimal(cliente.exo_points),
            article=cliente.exo_article,
            subsection=cliente.exo_subsection,
            institution_other=str(cliente.exo_institution_other or ""),
        )
        return Exoneracion(
            tipo_documento=exencion.document_type,
            numero_documento=exencion.document_number,
            nombre_institucion=exencion.institution,
            fecha=f"{exencion.date}T00:00:00{_DESFASE}",
            puntos=exencion.points,
            articulo=exencion.article,
            inciso=exencion.subsection,
            nombre_institucion_otros=exencion.institution_other,
        )

    # ------------------------------------------------------------ líneas

    def _productos(self, ids: list[int]) -> dict[int, Product]:
        if not ids:
            return {}
        filas = self._db.query(Product).filter(Product.id_product.in_(set(ids))).all()
        return {p.id_product: p for p in filas}

    @staticmethod
    def _impuesto(
        numero: int,
        tax_code: str | None,
        tax_rate: object,
        exoneracion: Exoneracion | None,
    ) -> Impuesto:
        codigo = (tax_code or "").strip() or suggested_code(TaxRate(_decimal(tax_rate)))
        if not codigo:
            raise ComprobanteInvalido("linea_sin_codigo_de_tarifa", numero)
        tarifa = rate_for(codigo).value * 100
        return Impuesto(
            codigo="01",
            codigo_tarifa=codigo,
            tarifa=tarifa,
            exoneracion=exoneracion if exoneracion is not None and tarifa > 0 else None,
        )

    def _linea(
        self,
        numero: int,
        *,
        producto: Product | None,
        product_id: int,
        cabys: str | None,
        unidad: str | None,
        cantidad: object,
        precio: object,
        tax_code: str | None,
        tax_rate: object,
        exoneracion: Exoneracion | None,
        export: bool = False,
        partida: str | None = None,
    ) -> Linea:
        cabys_final = (cabys or (producto.cabys_code if producto else None) or "").strip()
        if not cabys_final:
            raise ComprobanteInvalido("linea_sin_cabys", numero)
        detalle = (producto.name if producto and producto.name else f"Producto {product_id}").strip()
        unidad_final = (unidad or (producto.unit_of_measure if producto else None) or "").strip()
        # La partida, solo en la exportación (T-727): la de la línea, congelada
        # al cobrar, o la del producto si la línea es anterior a la 021. Que no
        # falte en una mercancía lo exige el armador.
        partida_final = (partida or (producto.tariff_heading if producto else None) or "").strip()
        return Linea(
            numero=numero,
            detalle=detalle[:200],
            cabys=cabys_final,
            cantidad=_decimal(cantidad),
            unidad=unidad_final or UNIDAD_POR_OMISION,
            precio_unitario=_decimal(precio),
            partida_arancelaria=partida_final if export else "",
            impuestos=(
                self._impuesto(
                    numero,
                    tax_code or (producto.tax_code if producto else None),
                    tax_rate,
                    exoneracion,
                ),
            ),
        )

    @staticmethod
    def _cierre(lineas: tuple[Linea, ...], medio: str) -> tuple[tuple[MedioPago, ...], Decimal]:
        """Los medios de pago y el IVA devuelto, que salen de las líneas."""
        total = sum((l.total_linea for l in lineas), Decimal(0))
        devuelto = vat_refund(
            [TaxedLine(cabys=l.cabys, tax=l.impuesto_neto) for l in lineas],
            [Payment(code=medio, amount=total)],
        )
        return (MedioPago(tipo=medio, monto=total - devuelto),), devuelto

    # ------------------------------------------------------------- venta

    def _venta(self, sale_id: int) -> Sale:
        venta = self._db.query(Sale).filter(Sale.id == sale_id).first()
        if venta is None:
            raise ComprobanteInvalido("venta_desconocida", sale_id)
        return venta

    def _detalles(self, sale_id: int) -> list[SaleDetail]:
        return (
            self._db.query(SaleDetail)
            .filter(SaleDetail.sale_id == sale_id)
            .order_by(SaleDetail.id)
            .all()
        )

    def _de_venta(self, doc: DocumentSnapshot, emisor: Parte, actividad: str) -> Comprobante:
        venta = self._venta(doc.source_id)
        detalles = self._detalles(venta.id)
        if not detalles:
            raise ComprobanteInvalido("venta_sin_lineas", venta.id)
        productos = self._productos([d.product_id for d in detalles])
        exporta = doc.document_type == EXPORT_INVOICE
        receptor, exoneracion = self._receptor(venta.client_id, export=exporta)
        lineas = tuple(
            self._linea(
                i,
                producto=productos.get(d.product_id),
                product_id=d.product_id,
                cabys=d.cabys_code,
                unidad=d.unit_of_measure,
                cantidad=d.quantity,
                precio=d.unit_price,
                tax_code=d.tax_code,
                tax_rate=d.tax_rate,
                exoneracion=exoneracion,
                export=exporta,
                partida=d.tariff_heading,
            )
            for i, d in enumerate(detalles, 1)
        )
        medios, devuelto = self._cierre(lineas, code_for(venta.payment_method))
        return Comprobante(
            tipo=doc.document_type,
            clave=doc.clave,
            consecutivo=doc.consecutive,
            fecha=_fecha(venta.created_at),
            emisor=emisor,
            condicion_venta=CONTADO,
            lineas=lineas,
            actividad_emisor=actividad,
            receptor=receptor,
            proveedor_sistemas=self._proveedor or emisor.identificacion.numero,
            medios_pago=medios,
            iva_devuelto=devuelto,
        )

    # -------------------------------------------------------- referencia

    def _referencia(self, venta: Sale, codigo: str | None, razon: str | None) -> Referencia:
        original = (
            self._db.query(FeDocument)
            .filter(FeDocument.source_type == SOURCE_SALE, FeDocument.source_id == venta.id)
            .order_by(FeDocument.id.desc())
            .first()
        )
        if original is None:
            raise ComprobanteInvalido("sin_comprobante_original", venta.id)
        return Referencia(
            tipo_documento=original.document_type,
            numero=original.clave,
            fecha=_fecha(venta.created_at),
            codigo=(codigo or "").strip(),
            razon=(razon or "").strip()[:180],
        )

    # -------------------------------------------------------- devolución

    def _de_devolucion(self, doc: DocumentSnapshot, emisor: Parte, actividad: str) -> Comprobante:
        devolucion = self._db.query(Return).filter(Return.id == doc.source_id).first()
        if devolucion is None:
            raise ComprobanteInvalido("devolucion_desconocida", doc.source_id)
        venta = self._venta(devolucion.sale_id)
        por_producto = {d.product_id: d for d in self._detalles(venta.id)}
        renglones = (
            self._db.query(ReturnDetail)
            .filter(ReturnDetail.return_id == devolucion.id)
            .order_by(ReturnDetail.id)
            .all()
        )
        if not renglones:
            raise ComprobanteInvalido("devolucion_sin_lineas", devolucion.id)
        productos = self._productos([r.product_id for r in renglones])
        receptor, exoneracion = self._receptor(venta.client_id)
        lineas = []
        for i, r in enumerate(renglones, 1):
            vendida = por_producto.get(r.product_id)
            lineas.append(
                self._linea(
                    i,
                    producto=productos.get(r.product_id),
                    product_id=r.product_id,
                    cabys=vendida.cabys_code if vendida else None,
                    unidad=vendida.unit_of_measure if vendida else None,
                    cantidad=r.quantity,
                    precio=r.unit_price,
                    tax_code=vendida.tax_code if vendida else None,
                    tax_rate=r.tax_rate,
                    exoneracion=exoneracion,
                )
            )
        lineas_t = tuple(lineas)
        medios, devuelto = self._cierre(lineas_t, CASH)
        return Comprobante(
            tipo=doc.document_type,
            clave=doc.clave,
            consecutivo=doc.consecutive,
            fecha=_fecha(devolucion.created_at),
            emisor=emisor,
            condicion_venta=CONTADO,
            lineas=lineas_t,
            actividad_emisor=actividad,
            receptor=receptor,
            proveedor_sistemas=self._proveedor or emisor.identificacion.numero,
            medios_pago=medios,
            referencias=(self._referencia(venta, devolucion.reference_code, devolucion.reason),),
            iva_devuelto=devuelto,
        )

    # -------------------------------------------------------------- nota

    def _de_nota(self, doc: DocumentSnapshot, emisor: Parte, actividad: str) -> Comprobante:
        nota = self._db.query(SaleNote).filter(SaleNote.id == doc.source_id).first()
        if nota is None:
            raise ComprobanteInvalido("nota_desconocida", doc.source_id)
        venta = self._venta(nota.sale_id)
        renglones = (
            self._db.query(SaleNoteLine)
            .filter(SaleNoteLine.note_id == nota.id)
            .order_by(SaleNoteLine.id)
            .all()
        )
        if not renglones:
            raise ComprobanteInvalido("nota_sin_lineas", nota.id)
        productos = self._productos([r.product_id for r in renglones])
        receptor, exoneracion = self._receptor(venta.client_id)
        lineas = tuple(
            self._linea(
                i,
                producto=productos.get(r.product_id),
                product_id=r.product_id,
                cabys=r.cabys_code,
                unidad=r.unit_of_measure,
                cantidad=1,
                precio=r.subtotal,
                tax_code=r.tax_code,
                tax_rate=r.tax_rate,
                exoneracion=exoneracion,
            )
            for i, r in enumerate(renglones, 1)
        )
        medio = code_for(nota.payment_method) if nota.payment_method else CASH
        medios, devuelto = self._cierre(lineas, medio)
        return Comprobante(
            tipo=doc.document_type,
            clave=doc.clave,
            consecutivo=doc.consecutive,
            fecha=_fecha(nota.created_at),
            emisor=emisor,
            condicion_venta=CONTADO,
            lineas=lineas,
            actividad_emisor=actividad,
            receptor=receptor,
            proveedor_sistemas=self._proveedor or emisor.identificacion.numero,
            medios_pago=medios,
            referencias=(self._referencia(venta, nota.reference_code, nota.reason),),
            iva_devuelto=devuelto,
        )

    # ------------------------------------------------------------- compra

    def _de_compra(self, doc: DocumentSnapshot, negocio: Parte, actividad: str) -> Comprobante:
        """La factura electrónica de compra (T-728, RF-79).

        La emite el negocio como comprador, así que en el XML **el emisor es el
        proveedor** no contribuyente y **el receptor es el negocio**, con la
        actividad del negocio en los dos: es lo que trae la FEC aceptada de
        `docs/`. La referencia es al documento de respaldo del proveedor (tipo
        14); sin número si no lo dio, que es lo normal en quien no factura. Lo
        que falte detiene el comprobante con su código, como en la venta.
        """
        compra = self._db.query(StockEntry).filter(StockEntry.id == doc.source_id).first()
        if compra is None:
            raise ComprobanteInvalido("compra_desconocida", doc.source_id)
        if compra.supplier_id is None:
            raise ComprobanteInvalido("compra_sin_proveedor", compra.id)
        proveedor = self._db.query(Supplier).filter(Supplier.id == compra.supplier_id).first()
        if proveedor is None:
            raise ComprobanteInvalido("proveedor_desconocido", compra.supplier_id)
        tipo = proveedor.identification_type or identification_type_for(proveedor.identification or "")
        numero = _digitos(proveedor.identification)
        if not tipo or not numero:
            raise ComprobanteInvalido("proveedor_sin_identificacion", proveedor.id)
        correo = str(proveedor.email or "").strip()
        vendedor = Parte(
            nombre=str(proveedor.name or "").strip()[:100] or numero,
            identificacion=Identificacion(tipo=tipo, numero=numero),
            telefono=_digitos(proveedor.phone)[:20],
            correo=correo if is_valid_email(correo) else "",
        )

        renglones = (
            self._db.query(StockEntryDetail)
            .filter(StockEntryDetail.entry_id == compra.id)
            .order_by(StockEntryDetail.id)
            .all()
        )
        if not renglones:
            raise ComprobanteInvalido("compra_sin_lineas", compra.id)
        productos = self._productos([r.product_id for r in renglones])
        lineas = []
        for i, r in enumerate(renglones, 1):
            producto = productos.get(r.product_id)
            # La tarifa es la del documento del proveedor (RN-53), en porcentaje;
            # el código lo decide el dominio (`purchase_line_code`).
            tarifa = TaxRate.percent(_decimal(r.tax_rate))
            lineas.append(
                self._linea(
                    i,
                    producto=producto,
                    product_id=r.product_id,
                    cabys=None,
                    unidad=None,
                    cantidad=r.quantity,
                    precio=r.unit_cost,
                    tax_code=purchase_line_code(producto.tax_code if producto else None, tarifa),
                    tax_rate=tarifa.value,
                    exoneracion=None,
                )
            )
        lineas_t = tuple(lineas)

        # La condición es la de la compra: a crédito lleva su plazo y ningún
        # medio de pago (RN-77); de contado, cómo se abonó, si se abonó.
        plazo = (
            credit_term_days(compra.document_date, compra.created_at.date(), compra.due_date)
            if compra.payment_terms == "credit"
            else None
        )
        a_credito = plazo is not None
        medios: tuple[MedioPago, ...] = ()
        if not a_credito:
            abono = (
                self._db.query(SupplierPayment)
                .filter(SupplierPayment.entry_id == compra.id)
                .order_by(SupplierPayment.id)
                .first()
            )
            medio, detalle = code_for_purchase(abono.method if abono else None)
            total = sum((l.total_linea for l in lineas_t), Decimal(0))
            medios = (MedioPago(tipo=medio, monto=total, detalle=detalle),)

        fecha_respaldo = (
            datetime.combine(compra.document_date, time()) if compra.document_date else compra.created_at
        )
        return Comprobante(
            tipo=doc.document_type,
            clave=doc.clave,
            consecutivo=doc.consecutive,
            fecha=_fecha(compra.created_at),
            emisor=vendedor,
            condicion_venta=CREDITO if a_credito else CONTADO,
            plazo_credito=plazo,
            lineas=lineas_t,
            actividad_emisor=actividad,
            receptor=negocio,
            actividad_receptor=actividad,
            proveedor_sistemas=self._proveedor or negocio.identificacion.numero,
            medios_pago=medios,
            referencias=(
                Referencia(
                    tipo_documento=REFERENCIA_RESPALDO,
                    numero=str(compra.document_number or "").strip()[:50],
                    fecha=_fecha(fecha_respaldo),
                    codigo=REFERS_TO_OTHER,
                ),
            ),
        )
