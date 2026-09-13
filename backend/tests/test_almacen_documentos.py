"""
El almacén de comprobantes: una batería, dos implementaciones (T-623).

Es el patrón de T-106: lo que se prueba no es el adaptador sino **el contrato**,
y la misma batería la corren el doble en memoria y el MinIO de verdad. Sin eso,
«va detrás de un puerto» significa que nadie sabrá si el puerto admitía dos
implementaciones hasta el día que haya que escribir la segunda.

La mitad de integración se omite —no falla— si la pila de pruebas no está
arriba, igual que el resto de la batería: un rojo por no haber levantado Docker
enseña a ignorar el rojo.
"""

from __future__ import annotations

import os

import pytest

from app.application.ports.documents import (
    DocumentAlreadyStored,
    DocumentNotFound,
    StorageUnavailable,
)
from app.domain.fe_documents import (
    GOV_RESPONSE,
    PRODUCTION,
    RECEIVED_PDF,
    SANDBOX,
    SIGNED_PAYLOAD,
    DocumentRef,
)
from tests.application.fakes import FakeDocumentStore
from tests.conftest import marca_unica

#: Publicado por `docker-compose.test.yml` en el 9002, que no choca con el 9000
#: de la pila de trabajo.
MINIO = os.environ.get("VENTASYS_TEST_MINIO", "http://127.0.0.1:9002")

pytestmark = pytest.mark.integration


def clave() -> str:
    """Una clave numérica distinta en cada llamada.

    El almacén se niega a pisar lo escrito —que es justo lo que se prueba—, así
    que dos pruebas con la misma clave se estorbarían: la segunda fallaría por
    lo que dejó la primera, y el mensaje señalaría el sitio equivocado. Y el
    bucket de la pila de pruebas sobrevive a la corrida, igual que la base.

    La marca va en el **consecutivo**, que son veinte dígitos, y no en el código
    de seguridad, que son ocho: con ocho, el reloj y el contador no caben y las
    claves empiezan a repetirse entre corridas.
    """
    consecutivo = marca_unica().rjust(20, "0")[-20:]
    return "506" + "1309" + "26" + "003101234567" + consecutivo + "1" + "12345678"


# --------------------------------------------------------------- las dos
# implementaciones


def _s3():
    boto3 = pytest.importorskip("boto3", reason="boto3 no está instalado")
    from botocore.exceptions import BotoCoreError, ClientError  # noqa: F401

    from app.infrastructure.storage.s3_documents import (
        S3DocumentStore,
        ensure_bucket,
        s3_client,
    )

    cliente = s3_client(
        endpoint=MINIO, access_key="test", secret_key="testtest"
    )
    bucket = "ventasys-fe-test"
    try:
        ensure_bucket(cliente, bucket)
    except StorageUnavailable as exc:
        pytest.skip(
            f"No hay MinIO en {MINIO} ({exc}). Levantalo con:\n"
            "  docker compose -f docker-compose.test.yml up -d --wait minio"
        )
    return S3DocumentStore(cliente, bucket)


@pytest.fixture(params=["doble", "minio"])
def almacen(request):
    """La misma batería, contra el doble y contra el almacén de verdad."""
    if request.param == "doble":
        return FakeDocumentStore()
    return _s3()


# ------------------------------------------------------------------ contrato


class TestElContrato:
    def test_lo_que_baja_es_byte_por_byte_lo_que_subio(self, almacen):
        # No es una obviedad: es la propiedad de la que depende que una firma
        # todavía verifique cinco años después. Se usa un XML con acentos y con
        # BOM porque es donde una codificación de más rompería la firma.
        xml = (
            b"\xef\xbb\xbf<?xml version='1.0' encoding='UTF-8'?>"
            b"<FacturaElectronica><Nombre>Compa\xc3\xb1\xc3\xada</Nombre></FacturaElectronica>"
        )
        ref = DocumentRef(1, PRODUCTION, SIGNED_PAYLOAD, clave())

        assert almacen.put(ref, xml) == ref.key
        assert almacen.get(ref) == xml

    def test_no_pisa_lo_ya_guardado(self, almacen):
        # El caso real: un reintento de la cola que llega tarde y sobreescribe
        # el acuse bueno con uno viejo.
        ref = DocumentRef(1, PRODUCTION, GOV_RESPONSE, clave())
        almacen.put(ref, b"<Mensaje>aceptado</Mensaje>")

        with pytest.raises(DocumentAlreadyStored) as e:
            almacen.put(ref, b"<Mensaje>rechazado</Mensaje>")

        assert e.value.key == ref.key
        # Y lo importante: el original sigue ahí.
        assert almacen.get(ref) == b"<Mensaje>aceptado</Mensaje>"

    def test_lo_que_no_esta_se_dice(self, almacen):
        ref = DocumentRef(1, SANDBOX, SIGNED_PAYLOAD, clave())
        with pytest.raises(DocumentNotFound):
            almacen.get(ref)
        assert almacen.exists(ref) is False

    def test_exists_no_baja_el_archivo(self, almacen):
        ref = DocumentRef(1, SANDBOX, RECEIVED_PDF, clave())
        almacen.put(ref, b"%PDF-1.4 fingido")
        assert almacen.exists(ref) is True

    def test_dos_companias_no_se_ven(self, almacen):
        # Es la razón de que la ruta la arme el servidor y empiece por la
        # compañía: con una ruta que pudiera escribir el cliente, esto no se
        # sostendría con ninguna prueba.
        misma = clave()
        de_uno = DocumentRef(1, PRODUCTION, SIGNED_PAYLOAD, misma)
        de_otro = DocumentRef(2, PRODUCTION, SIGNED_PAYLOAD, misma)

        almacen.put(de_uno, b"<de la compania 1/>")
        assert almacen.exists(de_otro) is False

        almacen.put(de_otro, b"<de la compania 2/>")
        assert almacen.get(de_uno) == b"<de la compania 1/>"
        assert almacen.get(de_otro) == b"<de la compania 2/>"

    def test_el_ensayo_y_la_factura_de_verdad_conviven(self, almacen):
        # La clave se arma con el consecutivo, y pruebas y producción se numeran
        # aparte: la misma clave puede ser dos documentos distintos.
        misma = clave()
        ensayo = DocumentRef(1, SANDBOX, SIGNED_PAYLOAD, misma)
        real = DocumentRef(1, PRODUCTION, SIGNED_PAYLOAD, misma)

        almacen.put(ensayo, b"<ensayo/>")
        almacen.put(real, b"<de verdad/>")

        assert almacen.get(ensayo) == b"<ensayo/>"
        assert almacen.get(real) == b"<de verdad/>"

    def test_un_documento_vacio_tambien_se_guarda(self, almacen):
        # Cero bytes es un contenido, no una ausencia: si el proveedor mandó un
        # PDF vacío, lo que hay que custodiar es ese.
        ref = DocumentRef(1, SANDBOX, RECEIVED_PDF, clave())
        almacen.put(ref, b"")
        assert almacen.get(ref) == b""
        assert almacen.exists(ref) is True


# ------------------------------------------------------- solo el de verdad


class TestContraMinIO:
    def test_el_bucket_se_crea_solo(self):
        # Un despliegue nuevo no debería necesitar que alguien entre a la
        # consola de MinIO antes de poder facturar.
        pytest.importorskip("boto3")
        from app.infrastructure.storage.s3_documents import ensure_bucket, s3_client

        cliente = s3_client(endpoint=MINIO, access_key="test", secret_key="testtest")
        nombre = f"prueba-{marca_unica()[-10:]}"
        try:
            ensure_bucket(cliente, nombre)
        except StorageUnavailable as exc:
            pytest.skip(f"No hay MinIO en {MINIO} ({exc})")

        # Y dos veces no falla: lo llama el arranque, que puede repetirse.
        ensure_bucket(cliente, nombre)
        cliente.delete_bucket(Bucket=nombre)

    def test_el_tipo_de_contenido_viaja(self):
        # Para que la consola de MinIO y cualquier navegador muestren el XML
        # como XML en vez de ofrecer una descarga sin nombre.
        pytest.importorskip("boto3")
        almacen = _s3()
        ref = DocumentRef(1, PRODUCTION, SIGNED_PAYLOAD, clave())
        almacen.put(ref, b"<x/>")

        cabecera = almacen._s3.head_object(Bucket=almacen._bucket, Key=ref.key)
        assert cabecera["ContentType"] == "application/xml"

    def test_sin_almacen_no_se_confirma_nada(self):
        # El modo de falla que importa: si el almacén no contesta, quien llama
        # tiene que poder NO confirmar la transacción. Por eso es una excepción
        # propia y no un error de boto3 que se escape como un 500.
        pytest.importorskip("boto3")
        from app.infrastructure.storage.s3_documents import S3DocumentStore, s3_client

        # Un puerto donde no hay nada escuchando.
        muerto = S3DocumentStore(
            s3_client(endpoint="http://127.0.0.1:9", access_key="x", secret_key="y"),
            "loquesea",
        )
        with pytest.raises(StorageUnavailable):
            muerto.put(DocumentRef(1, SANDBOX, SIGNED_PAYLOAD, clave()), b"<x/>")
