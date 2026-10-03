"""
El recorrido hasta Hacienda, contra el stack real (F7, T-707 a T-713, T-721).

Hacienda es la de mentira de `tests/stub_hacienda.py`, que la pila de pruebas
levanta y a la que la API apunta por los overrides del compose. Vault y MinIO
son de verdad: el comprobante se firma con una llave importada a Vault y el XML
y la respuesta quedan en el almacén. La cola corre dentro del contenedor cada
segundo, así que lo que acá se espera es lo que la pantalla vería.

Toca la configuración y las credenciales de la compañía A y las deja como
estaban. El certificado que se sube es uno generado en la prueba: Vault no
distingue uno de Hacienda de uno de mentira, y el stub no valida la firma.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from .conftest import Api, codigo, marca_unica
from .test_documento_impreso import clasificar
from .test_compras import comprar, no_contribuyente
from .test_tipo_de_comprobante import PARTIDA, cliente_de, cliente_extranjero, exportable, venta

pytestmark = pytest.mark.characterization

PIN = "1234"
EVENTOS_FINALES = ("accepted", "rejected", "stopped")


def p12_de_prueba() -> bytes:
    llave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SWS DE PRUEBA")])
    ahora = datetime.now(timezone.utc)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nombre)
        .issuer_name(nombre)
        .public_key(llave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - timedelta(days=1))
        .not_valid_after(ahora + timedelta(days=30))
        .sign(llave, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        b"prueba", llave, certificado, None, serialization.BestAvailableEncryption(PIN.encode())
    )


@pytest.fixture
def emisor_listo(api: Api, facturacion):
    """Facturación encendida, certificado en Vault y usuario de ATV guardado."""
    facturacion(True)
    # La actividad económica va en el XML y la fixture de facturación no la pone.
    guardado = api.ok("GET", "/settings/")
    datos = dict(guardado["data"] or {})
    datos["eInvoicing"] = {**(datos.get("eInvoicing") or {}), "enabled": True, "economicActivity": "474100"}
    api.ok("PUT", "/settings/", {"data": datos, "keep_logo": True})
    estado, cuerpo = api.multipart(
        "/fe/sandbox/certificate",
        files={"archivo": ("prueba.p12", p12_de_prueba(), "application/x-pkcs12")},
        data={"pin": PIN},
    )
    assert estado == 200, cuerpo
    api.ok(
        "PUT",
        "/fe/sandbox/atv",
        {"user": "cpj-3101702934@stag.comprobanteselectronicos.go.cr", "password": "buena"},
    )
    yield
    api.call("DELETE", "/fe/sandbox/certificate")


def con_cabys(api: Api, producto: dict) -> dict:
    """Un producto que puede ir en un comprobante: con su CABYS y su unidad."""
    clasificar(api, producto, cabys="2316100000100", unidad="Unid")
    return producto


def comprobante_de(api: Api, id_sale: int) -> dict:
    return api.ok("GET", f"/sales/sale/{id_sale}")["einvoice"]


def esperar(api: Api, document_id: int, *, hasta: tuple[str, ...] = EVENTOS_FINALES, segundos: float = 30) -> dict:
    """La cola corre sola cada segundo; se espera a que el documento llegue."""
    limite = time.time() + segundos
    expediente = api.ok("GET", f"/fe/documents/{document_id}")
    while expediente["document"]["status"] not in hasta and time.time() < limite:
        time.sleep(0.5)
        expediente = api.ok("GET", f"/fe/documents/{document_id}")
    return expediente


class TestElRecorridoEntero:
    def test_un_tiquete_llega_a_aceptado_con_su_xml_y_su_respuesta(self, api: Api, producto, emisor_listo):
        p = con_cabys(api, producto("Tiquete que viaja", 1000, 5))
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p))
        numerado = comprobante_de(api, hecha["id_sale"])
        assert numerado["status"] in ("numbered", "signed", "sent", "accepted")

        expediente = esperar(api, numerado["id"])
        documento = expediente["document"]
        assert documento["status"] == "accepted", expediente
        assert documento["hacienda_status"] == "aceptado"
        assert documento["has_xml"] and documento["has_response"]
        assert documento["signed_at"] and documento["sent_at"] and documento["resolved_at"]
        assert documento["next_attempt_at"] is None
        assert [e["event"] for e in expediente["events"]] == ["signed", "sent", "accepted"]
        assert documento["stop_detail"] == "Aceptado por la prueba"

        # El XML que se bajó es el que se firmó, con la firma adentro y la clave.
        estado, xml = api.call("GET", f"/fe/documents/{documento['id']}/xml")
        assert estado == 200
        texto = xml if isinstance(xml, str) else str(xml)
        assert "<ds:Signature" in texto and numerado["clave"] in texto
        estado, respuesta = api.call("GET", f"/fe/documents/{documento['id']}/response")
        assert estado == 200
        assert "<Mensaje>1</Mensaje>" in (respuesta if isinstance(respuesta, str) else str(respuesta))

        # Y la venta lo sabe: el detalle y el listado dicen «aceptado».
        assert comprobante_de(api, hecha["id_sale"])["status"] == "accepted"
        fila = next(v for v in api.ok("GET", "/sales/sales_list") if v["id"] == hecha["id_sale"])
        assert fila["einvoice_status"] == "accepted"

    def test_una_factura_con_cliente_tambien_viaja(self, api: Api, producto, emisor_listo):
        p = con_cabys(api, producto("Factura que viaja", 1000, 5))
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p, client_id=cliente_de(api)))
        documento = esperar(api, comprobante_de(api, hecha["id_sale"])["id"])["document"]
        assert documento["status"] == "accepted", documento
        assert documento["document_type"] == "01"

    def test_la_devolucion_emite_su_nota_y_la_nota_viaja(self, api: Api, producto, emisor_listo):
        p = con_cabys(api, producto("Se devuelve", 1000, 5))
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p))
        esperar(api, comprobante_de(api, hecha["id_sale"])["id"])
        devuelta = api.ok(
            "POST",
            "/returns/add_return",
            {
                "sale_id": hecha["id_sale"],
                "user_id": api.user_id,  # type: ignore[attr-defined]
                "reason": "Vino golpeado",
                "items": [{"id_product": p["id_product"], "quantity": 1}],
            },
        )
        nota = api.ok("GET", f"/returns/return/{devuelta['id_return']}")["einvoice"]
        assert nota["document_type"] == "03"
        documento = esperar(api, nota["id"])["document"]
        assert documento["status"] == "accepted", documento


class TestLoQueSeDetiene:
    def test_sin_certificado_se_detiene_y_se_puede_reintentar(self, api: Api, producto, facturacion):
        facturacion(True)
        api.call("DELETE", "/fe/sandbox/certificate")
        p = producto("Sin certificado", 1000, 5)
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p))
        documento = esperar(api, comprobante_de(api, hecha["id_sale"])["id"])["document"]
        assert (documento["status"], documento["stop_reason"]) == ("stopped", "certificate_missing")

        # Está en la lista de lo detenido, con su antigüedad.
        cola = api.ok("GET", "/fe/queue")
        assert any(d["id"] == documento["id"] for d in cola["stopped"])
        assert cola["counts"]["stopped"] >= 1

        # Reintentar lo devuelve a la cola; sin certificado se vuelve a detener.
        reintentado = api.ok("POST", f"/fe/documents/{documento['id']}/retry")
        assert reintentado["document"]["status"] in ("numbered", "stopped")
        assert any(e["event"] == "resumed" for e in reintentado["events"])
        de_nuevo = esperar(api, documento["id"])["document"]
        assert de_nuevo["stop_reason"] == "certificate_missing"

        # Sin firmar no hay XML que bajar, y lo dice con su código.
        estado, cuerpo = api.call("GET", f"/fe/documents/{documento['id']}/xml")
        assert estado == 409 and cuerpo["detail"]["code"] == "document_not_signed"

    def test_credenciales_rechazadas_detienen_en_el_primer_intento(self, api: Api, producto, emisor_listo):
        api.ok(
            "PUT",
            "/fe/sandbox/atv",
            {"user": "cpj-3101702934@stag.comprobanteselectronicos.go.cr", "password": "mala"},
        )
        p = con_cabys(api, producto("Credenciales malas", 1000, 5))
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p))
        documento = esperar(api, comprobante_de(api, hecha["id_sale"])["id"])["document"]
        assert (documento["status"], documento["stop_reason"]) == ("stopped", "credentials_rejected")
        assert documento["has_xml"] is True  # se firmó; lo que falló fue el envío

    def test_el_que_no_esta_detenido_no_se_reintenta(self, api: Api, producto, emisor_listo):
        p = con_cabys(api, producto("Aceptado", 1000, 5))
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p))
        documento = esperar(api, comprobante_de(api, hecha["id_sale"])["id"])["document"]
        assert documento["status"] == "accepted"
        respuesta = api.call("POST", f"/fe/documents/{documento['id']}/retry")
        assert codigo(respuesta, 409) == "document_not_stopped"


class TestLaPuertaDeProduccion:
    """T-713, RN-46, y lo de RN-35 que antes vivía en `test_credenciales_fe_http.py`
    y ya no puede: desde que la puerta existe, a producción solo se llega con una
    factura, un tiquete y una nota de crédito aceptados en pruebas."""

    def test_dice_que_falta_hasta_que_los_tres_esten_aceptados(self, api: Api, facturacion):
        facturacion(True)
        estado = api.ok("GET", "/fe")
        puerta = estado["production_gate"]
        assert set(puerta["missing"]) <= {"01", "04", "03"}
        if puerta["missing"]:
            respuesta = api.call("PUT", "/fe/active", {"environment": "production", "confirm": True})
            assert codigo(respuesta, 409) == "production_gate_locked"
            assert respuesta[1]["detail"]["missing"] == puerta["missing"]
        else:
            assert puerta["ready"] is True

    def test_con_los_tres_aceptados_se_pasa_y_el_ambiente_se_conserva(
        self, api: Api, soporte: Api, producto, emisor_listo
    ):
        # Un tiquete, una factura y la nota de crédito de devolver el tiquete.
        p = con_cabys(api, producto("Para la puerta", 1000, 9))
        tiquete = api.ok("POST", "/sales/add_sale", venta(api, p))
        factura = api.ok("POST", "/sales/add_sale", venta(api, p, client_id=cliente_de(api)))
        esperar(api, comprobante_de(api, tiquete["id_sale"])["id"])
        devuelta = api.ok(
            "POST",
            "/returns/add_return",
            {
                "sale_id": tiquete["id_sale"],
                "user_id": api.user_id,  # type: ignore[attr-defined]
                "reason": "Para la puerta",
                "items": [{"id_product": p["id_product"], "quantity": 1}],
            },
        )
        for documento in (
            comprobante_de(api, factura["id_sale"]),
            api.ok("GET", f"/returns/return/{devuelta['id_return']}")["einvoice"],
        ):
            assert esperar(api, documento["id"])["document"]["status"] == "accepted"

        puerta = api.ok("GET", "/fe")["production_gate"]
        assert puerta == {"ready": True, "missing": []}
        try:
            # RN-35: confirmado, sí.
            hecho = api.ok("PUT", "/fe/active", {"environment": "production", "confirm": True})
            assert hecho["active"] == "production"
            # Guardar la configuración sin la sección no borra el ambiente (F6).
            actual = api.ok("GET", "/settings/")
            datos = {k: v for k, v in actual["data"].items() if k != "eInvoicing"}
            api.ok("PUT", "/settings/", {"data": datos, "keep_logo": True})
            assert api.ok("GET", "/fe")["active"] == "production"
            # Y queda en bitácora con el antes y el después (RN-35, T-611).
            estado, bitacora = soporte.call("GET", "/support/audit?accion=fe_ambiente&limit=20")
            if estado == 200:
                assert "sandbox → production" in [l["detalle"] for l in bitacora["lineas"]]
        finally:
            # Volver a pruebas no pide confirmación (RN-35), y deja todo como estaba.
            vuelta = api.ok("PUT", "/fe/active", {"environment": "sandbox"})
            assert vuelta["active"] == "sandbox"


#: El archivo de cada tipo en `docs/hacienda/costa-rica/esquemas/`.
XSD_DE = {
    "08": "FacturaElectronicaCompra_V4.4.xsd",
    "09": "FacturaElectronicaExportacion_V4.4.xsd",
}


def valida_contra_su_xsd(xml: str, tipo: str, tmp_path) -> None:
    """El XML que armó el adaptador real, firmado, contra el XSD oficial.

    Es lo que la Hacienda de mentira no hace: acepta todo. Sin esto, la única
    validación contra el esquema sería la de comprobantes armados a mano en el
    dominio, y un dato mal puesto por el adaptador llegaría al sandbox real.
    """
    import shutil
    from pathlib import Path

    etree = pytest.importorskip("lxml.etree", reason="lxml no está instalado")
    esquemas = Path(__file__).resolve().parents[2] / "docs" / "hacienda" / "costa-rica" / "esquemas"
    # El XSD importa `../../xmldsig-core-schema.xsd`: se reproduce la carpeta.
    hondo = tmp_path / "v4" / "4"
    hondo.mkdir(parents=True, exist_ok=True)
    for archivo in esquemas.glob("*.xsd"):
        shutil.copy2(archivo, hondo / archivo.name)
    shutil.copy2(esquemas / "xmldsig-core-schema.xsd", tmp_path / "xmldsig-core-schema.xsd")
    esquema = etree.XMLSchema(etree.parse(str(hondo / XSD_DE[tipo])))
    esquema.assertValid(etree.fromstring(xml.encode("utf-8")))


def con_tipos(api: Api, tipos: list[str]) -> None:
    """Lo que la compañía emite (RN-88); `facturacion` lo deshace al terminar."""
    guardado = api.ok("GET", "/settings/")["data"] or {}
    seccion = dict(guardado.get("eInvoicing") or {})
    seccion["documentTypes"] = tipos
    api.ok("PUT", "/settings/", {"data": {**guardado, "eInvoicing": seccion}, "keep_logo": True})


def con_exportacion(api: Api) -> None:
    con_tipos(api, ["01", "04", "03", "02", "09"])


class TestLaFacturaDeCompra:
    """T-728: la FEC recorre la cola como las demás y su XML es el de compra:
    el proveedor como emisor, el negocio como receptor con su actividad en los
    dos, y la referencia al respaldo del proveedor."""

    def test_una_compra_a_un_no_contribuyente_llega_a_aceptada(
        self, api: Api, producto, emisor_listo, tmp_path
    ):
        con_tipos(api, ["01", "04", "03", "02", "08"])
        p = con_cabys(api, producto("Verduras del mercado", 1000, 0))
        # Con el impuesto en la línea, como lo teclea una persona cuando el
        # recibo del no contribuyente no lo trae (RN-53): la FEC lleva el de la
        # compra, y un 0 % tiene tres códigos que nadie adivina (RN-80).
        compra = comprar(
            api,
            no_contribuyente(api),
            p,
            payment_terms="cash",
            lines=[{"id_product": p["id_product"], "quantity": 1, "unit_cost": 1000, "tax_rate": 13, "tax_amount": 130}],
        )
        numerado = api.ok("GET", f"/inventory/entry/{compra['id_entry']}")["einvoice"]
        assert numerado["document_type"] == "08"

        expediente = esperar(api, numerado["id"])
        assert expediente["document"]["status"] == "accepted", expediente

        estado, xml = api.call("GET", f"/fe/documents/{numerado['id']}/xml")
        assert estado == 200
        texto = xml if isinstance(xml, str) else str(xml)
        assert "FacturaElectronicaCompra" in texto
        emisor_xml = texto.split("<Emisor>")[1].split("</Emisor>")[0]
        receptor_xml = texto.split("<Receptor>")[1].split("</Receptor>")[0]
        assert "<Tipo>06</Tipo>" in emisor_xml
        assert "<Tipo>06</Tipo>" not in receptor_xml
        assert "<CodigoActividadEmisor>474100</CodigoActividadEmisor>" in texto
        assert "<CodigoActividadReceptor>474100</CodigoActividadReceptor>" in texto
        assert "<TipoDocIR>14</TipoDocIR>" in texto
        assert "<Codigo>04</Codigo>" in texto.split("<InformacionReferencia>")[1]
        valida_contra_su_xsd(texto, "08", tmp_path)


class TestLaExportacion:
    """T-727: la FEE recorre la cola igual que las otras y su XML es el de
    exportación: receptor `05` con sus señas y sin ubicación, la partida en la
    línea y la raíz de la 4.4."""

    def test_una_exportacion_llega_a_aceptada_con_su_xml(
        self, api: Api, producto, emisor_listo, tmp_path
    ):
        con_exportacion(api)
        p = exportable(api, producto("Café para exportar", 1000, 5))
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p, client_id=cliente_extranjero(api)))
        numerado = comprobante_de(api, hecha["id_sale"])
        assert numerado["document_type"] == "09"

        expediente = esperar(api, numerado["id"])
        assert expediente["document"]["status"] == "accepted", expediente

        estado, xml = api.call("GET", f"/fe/documents/{numerado['id']}/xml")
        assert estado == 200
        texto = xml if isinstance(xml, str) else str(xml)
        assert "FacturaElectronicaExportacion" in texto
        assert "<Tipo>05</Tipo>" in texto
        assert "<OtrasSenasExtranjero>" in texto
        assert f"<PartidaArancelaria>{PARTIDA}</PartidaArancelaria>" in texto
        # Lo que el perfil 09 no admite no está (T-720).
        assert "<Ubicacion>" not in texto.split("<Receptor>")[1].split("</Receptor>")[0]
        assert "<Exoneracion>" not in texto
        assert "<TotalNoSujeto>" not in texto
        valida_contra_su_xsd(texto, "09", tmp_path)


class TestElAislamiento:
    def test_la_otra_compania_no_ve_el_comprobante(self, api: Api, api_b: Api, producto, emisor_listo):
        p = con_cabys(api, producto("Ajeno", 1000, 5))
        hecha = api.ok("POST", "/sales/add_sale", venta(api, p))
        documento = comprobante_de(api, hecha["id_sale"])
        for ruta in ("", "/xml", "/response"):
            estado, _ = api_b.call("GET", f"/fe/documents/{documento['id']}{ruta}")
            assert estado == 404, ruta
        estado, _ = api_b.call("POST", f"/fe/documents/{documento['id']}/retry")
        assert estado == 404
        assert all(d["id"] != documento["id"] for d in api_b.ok("GET", "/fe/queue")["stopped"])
