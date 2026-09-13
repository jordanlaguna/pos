"""
Abrir un `.p12` de verdad (T-603, T-606).

Se arma uno en la prueba con `cryptography` en vez de guardar un archivo en el
repositorio: un `.p12` versionado es una llave privada versionada, aunque sea de
juguete, y además vencería.
"""

from __future__ import annotations

import datetime as dt

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from app.application.ports.signing import InvalidCertificate
from app.infrastructure.crypto.pkcs12_reader import Pkcs12CertificateReader

PIN = "clave-del-p12"


def armar_p12(
    *,
    nombre: str = "PANADERÍA LA ESPIGA S.A.",
    dias: int = 365,
    pin: str = PIN,
    con_llave: bool = True,
    sin_common_name: bool = False,
) -> tuple[bytes, dt.datetime]:
    """Un `.p12` como el que emite ATV, y cuándo vence (en hora local)."""
    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    atributos = [x509.NameAttribute(NameOID.COUNTRY_NAME, "CR")]
    if not sin_common_name:
        atributos.append(x509.NameAttribute(NameOID.COMMON_NAME, nombre))
    sujeto = x509.Name(atributos)

    # El «desde» se cuelga del «hasta» y no del reloj: con `dias` negativo
    # —un certificado ya vencido, que hay que poder leer igual— un `desde`
    # anclado a hoy quedaría después del vencimiento y `cryptography` se niega
    # a armar el certificado.
    hasta = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=dias)
    desde = hasta - dt.timedelta(days=365)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(sujeto)
        .issuer_name(sujeto)
        .public_key(privada.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(desde)
        .not_valid_after(hasta)
        .sign(privada, hashes.SHA256())
    )

    crudo = pkcs12.serialize_key_and_certificates(
        name=b"llave",
        key=privada if con_llave else None,
        cert=certificado,
        cas=None,
        encryption_algorithm=(
            serialization.BestAvailableEncryption(pin.encode())
            if pin
            else serialization.NoEncryption()
        ),
    )
    return crudo, hasta.astimezone().replace(tzinfo=None)


class TestLoQueSeSaca:
    def test_la_publica_en_PEM_y_la_privada_en_PKCS8(self):
        crudo, _ = armar_p12()
        leido = Pkcs12CertificateReader().read(crudo, PIN)

        assert leido.certificate_pem.startswith("-----BEGIN CERTIFICATE-----")
        # Y que la privada sirva de verdad: es lo que se le manda a Vault.
        assert serialization.load_der_private_key(leido.private_key_der, password=None)

    def test_el_nombre_sale_del_certificado(self):
        crudo, _ = armar_p12(nombre="MI NEGOCIO S.A.")
        assert Pkcs12CertificateReader().read(crudo, PIN).subject == "MI NEGOCIO S.A."

    def test_sin_common_name_igual_se_puede_nombrar(self):
        # Feo pero cierto, que es mejor que vacío.
        crudo, _ = armar_p12(sin_common_name=True)
        assert Pkcs12CertificateReader().read(crudo, PIN).subject

    def test_el_vencimiento_viene_en_hora_local_y_sin_zona(self):
        """La conversión que importa.

        `cryptography` devuelve UTC con zona y todo el resto del sistema
        trabaja en hora local sin zona. Compararlo con `Clock.now()` —que es
        naíf— lanzaría `TypeError`, y guardarlo en UTC haría que un certificado
        que vence a las 18:00 se mostrara venciendo al día siguiente.
        """
        crudo, esperado = armar_p12(dias=200)
        leido = Pkcs12CertificateReader().read(crudo, PIN)

        assert leido.expires_at.tzinfo is None
        assert abs((leido.expires_at - esperado).total_seconds()) < 2
        # Y que se pueda comparar con un `datetime` naíf sin reventar.
        assert leido.expires_at > dt.datetime.now()

    def test_uno_ya_vencido_se_lee_igual(self):
        # Avisar no es impedir: el sistema tiene que poder decir «este venció»,
        # y para eso hay que poder abrirlo.
        crudo, _ = armar_p12(dias=-10)
        assert Pkcs12CertificateReader().read(crudo, PIN).expires_at < dt.datetime.now()


class TestLoQueSeRechaza:
    def test_un_PIN_equivocado(self):
        crudo, _ = armar_p12()
        with pytest.raises(InvalidCertificate) as e:
            Pkcs12CertificateReader().read(crudo, "no-es")
        assert e.value.reason == "bad_pin"

    @pytest.mark.parametrize(
        "otra_cosa, que_es",
        [
            (b"-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----", "el .cer de al lado"),
            (b"PK\x03\x04restodelzip", "un ZIP"),
            (b"%PDF-1.7", "un PDF"),
            (b"", "nada"),
        ],
    )
    def test_lo_que_no_es_un_p12_se_distingue_del_PIN_malo(self, otra_cosa, que_es):
        # La distinción existe porque lo que hay que hacer es distinto: volver a
        # escribir el PIN, o ir a buscar el archivo correcto.
        with pytest.raises(InvalidCertificate) as e:
            Pkcs12CertificateReader().read(otra_cosa, PIN)
        assert e.value.reason == "not_a_p12", que_es

    def test_un_p12_sin_llave_privada(self):
        # Pasa al exportar desde el navegador sin marcar «incluir la llave
        # privada». El archivo es válido y no sirve para firmar.
        crudo, _ = armar_p12(con_llave=False, pin="")
        with pytest.raises(InvalidCertificate) as e:
            Pkcs12CertificateReader().read(crudo, "")
        assert e.value.reason == "no_private_key"
