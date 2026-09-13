"""
El firmante contra Vault transit (T-602b, plan §7.1).

La llave privada se **importa** a Vault al subir el `.p12` y no vuelve a salir:
desde entonces, firmar es mandarle el digest y recibir la firma. Por eso la base
no guarda ni el `.p12` ni su PIN, y un respaldo robado no contiene ninguna llave
de firma.

Se le habla con `urllib` y no con un cliente de Vault, igual que el adaptador de
CABYS le habla a Hacienda: son cuatro endpoints, y el proyecto acota sus
dependencias a propósito —fue `passlib` lo que rompió una instalación entera—.

CÓMO ENTRA UNA LLAVE PROPIA (BYOK)
----------------------------------

No se puede mandar la privada en claro, ni siquiera por la red interna, así que
Vault define un baile de tres pasos que hay que hacer completo:

1. Se pide la **llave de envoltura** de Vault: una RSA-4096 pública.
2. Se sortea una AES-256 **efímera**, se envuelve la privada con ella
   (AES-KWP, RFC 5649) y se cifra la efímera con la RSA-4096 (OAEP/SHA-256).
3. Se manda la concatenación de las dos. Vault abre la efímera con su privada,
   y con la efímera abre la nuestra.

La efímera existe porque una RSA-4096 no puede cifrar directamente una clave de
2048 bits más su estructura: OAEP deja unos 446 bytes útiles y una PKCS#8 de
2048 bits pasa de 1 200.

`cryptography` trae las dos piezas —`aes_key_wrap_with_padding` y `OAEP`—, así
que acá no se implementa criptografía, se la ordena.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.keywrap import aes_key_wrap_with_padding

from app.application.ports.signing import SigningKeyMissing, SigningUnavailable
from app.domain.hacienda import signing_key_name

#: Corto. Quien espera esto es una transacción abierta o un trabajador de fondo,
#: no una persona mirando una pantalla; si Vault no contesta, lo que hay que
#: hacer es dejar el documento en la cola.
TIMEOUT_SECONDS = 10

#: Los tamaños de RSA que admite transit. Un certificado de Hacienda es de 2048;
#: los otros dos están porque un `.p12` emitido con más bits no tiene por qué
#: rebotar, y porque el mensaje de error de Vault ante un tipo que no coincide
#: no dice cuál era el correcto.
_TIPOS_RSA = {2048: "rsa-2048", 3072: "rsa-3072", 4096: "rsa-4096"}

#: Bytes de la AES efímera del paso 2. 32 = AES-256.
_EFIMERA_BYTES = 32


class VaultDocumentSigner:
    """Implementa `DocumentSigner` contra el motor `transit` de Vault."""

    def __init__(self, address: str, token: str, *, mount: str = "transit") -> None:
        self._base = address.rstrip("/")
        self._token = token
        self._mount = mount

    # ------------------------------------------------------------------ HTTP

    def _pedir(self, metodo: str, ruta: str, cuerpo: dict | None = None) -> dict:
        datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
        peticion = urllib.request.Request(
            f"{self._base}{ruta}",
            data=datos,
            method=metodo,
            headers={
                "X-Vault-Token": self._token,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(peticion, timeout=TIMEOUT_SECONDS) as respuesta:
                crudo = respuesta.read()
                return json.loads(crudo) if crudo else {}
        except urllib.error.HTTPError as exc:
            # 404 es «no existe» y lo traduce quien llama, que es el único que
            # sabe si eso significa «no hay certificado» o «no pasa nada».
            if exc.code == 404:
                raise _NoEsta() from exc
            # 503 es Vault sellado o en espera. Es el modo de falla que hay que
            # distinguir: se reintenta, no se reconfigura.
            #
            # El texto de Vault viaja en la excepción y no se descarta: es lo
            # único que quien opera va a tener cuando esto falle a las seis de
            # la mañana. No llega a ninguna pantalla —RN-30— pero sí a la traza.
            raise SigningUnavailable(f"Vault respondió {exc.code}: {_texto(exc)}") from exc
        except Exception as exc:  # noqa: BLE001 — red, DNS, TLS, JSON partido
            raise SigningUnavailable(str(exc)) from exc

    # --------------------------------------------------------------- importar

    def import_key(self, pkcs8_der: bytes, *, company_id: int, environment: str) -> None:
        nombre = signing_key_name(company_id, environment)
        tipo = _tipo_de(pkcs8_der)
        envoltorio = self._envolver(pkcs8_der)

        # Si la llave ya está, esto es un REEMPLAZO de certificado y va como
        # versión nueva. Importar sobre una que existe es un error en Vault, y
        # tratarlo como tal obligaría a borrar antes — o sea, a dejar una
        # ventana en la que la compañía no puede firmar.
        ruta = f"/v1/{self._mount}/keys/{nombre}"
        try:
            self._pedir("GET", ruta)
            destino = f"{ruta}/import_version"
            cuerpo = {"ciphertext": envoltorio}
        except _NoEsta:
            destino = f"{ruta}/import"
            cuerpo = {"ciphertext": envoltorio, "type": tipo, "hash_function": "SHA256"}

        try:
            self._pedir("POST", destino, cuerpo)
        except _NoEsta as exc:  # pragma: no cover — el motor transit sin montar
            raise SigningUnavailable(
                f"el motor «{self._mount}» no está montado en Vault"
            ) from exc

    def _envolver(self, pkcs8_der: bytes) -> str:
        """Los tres pasos del BYOK, en base64."""
        try:
            publica_pem = self._pedir("GET", f"/v1/{self._mount}/wrapping_key")["data"][
                "public_key"
            ]
        except _NoEsta as exc:
            raise SigningUnavailable(
                f"el motor «{self._mount}» no está montado en Vault"
            ) from exc

        efimera = os.urandom(_EFIMERA_BYTES)
        envuelta = aes_key_wrap_with_padding(efimera, pkcs8_der)

        publica = serialization.load_pem_public_key(publica_pem.encode("ascii"))
        cifrada = publica.encrypt(
            efimera,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        # El orden importa y es el que fija Vault: primero la efímera cifrada
        # —512 bytes, que es el tamaño de la RSA-4096— y después la llave.
        return base64.b64encode(cifrada + envuelta).decode("ascii")

    # ------------------------------------------------------------------ firmar

    def sign(self, digest: bytes, *, company_id: int, environment: str) -> bytes:
        nombre = signing_key_name(company_id, environment)
        try:
            respuesta = self._pedir(
                "POST",
                f"/v1/{self._mount}/sign/{nombre}",
                {
                    "input": base64.b64encode(digest).decode("ascii"),
                    # El digest ya viene hecho: acá no se vuelve a resumir.
                    "prehashed": True,
                    "hash_algorithm": "sha2-256",
                    # Lo que pide XAdES-EPES. El de fábrica de Vault es PSS, que
                    # Hacienda no acepta.
                    "signature_algorithm": "pkcs1v15",
                },
            )
        except _NoEsta as exc:
            raise SigningKeyMissing(company_id, environment) from exc
        except SigningUnavailable as exc:
            # **Firmar sin llave contesta 400 y no 404**, con el texto «signing
            # key not found» (comprobado contra Vault 1.20.4 el 2026-09-13). Se
            # pregunta por la llave en vez de leer ese texto: el mensaje puede
            # cambiar entre versiones y la existencia no.
            #
            # La diferencia no es cosmética. `SigningUnavailable` significa
            # «reintentá» y `SigningKeyMissing` significa «andá a cargar el
            # certificado»: confundirlas deja la cola reintentando para siempre
            # un documento que no va a firmarse nunca.
            if not self._existe(company_id, environment):
                raise SigningKeyMissing(company_id, environment) from exc
            raise

        # Viene como «vault:v1:<base64>». La versión va adentro a propósito: es
        # lo que permite saber con qué versión de la llave se firmó un
        # comprobante sin guardarlo en ninguna columna.
        firma = respuesta["data"]["signature"]
        return base64.b64decode(firma.rsplit(":", 1)[-1])

    def _existe(self, company_id: int, environment: str) -> bool:
        """Si hay llave para esa compañía y ese ambiente.

        Con Vault caído devuelve `True`, y es deliberado: `sign` ya falló por
        eso y lo que corresponde es que el desenlace siga siendo «reintentá».
        Decir «no hay llave» porque no se pudo preguntar mandaría a alguien a
        subir un certificado que ya está.
        """
        nombre = signing_key_name(company_id, environment)
        try:
            self._pedir("GET", f"/v1/{self._mount}/keys/{nombre}")
            return True
        except _NoEsta:
            return False
        except SigningUnavailable:
            return True

    # ------------------------------------------------------------------ quitar

    def forget_key(self, *, company_id: int, environment: str) -> None:
        nombre = signing_key_name(company_id, environment)
        ruta = f"/v1/{self._mount}/keys/{nombre}"
        try:
            # Se consulta ANTES de configurar, y no es un paso de más: ante una
            # llave que no existe, el endpoint de configuración contesta **400**
            # y no 404, así que sin esta consulta «quitar dos veces» se vería
            # como una falla de Vault. Comprobado el 2026-09-13 contra 1.20.4.
            self._pedir("GET", ruta)
        except _NoEsta:
            # Quitar lo que no está es el estado que se pedía, no un error.
            return

        # Transit se niega a borrar una llave que no lo autorizó primero. Es una
        # protección de Vault contra el borrado accidental, y hay que levantarla
        # a propósito para poder cumplir RF-24.
        self._pedir("POST", f"{ruta}/config", {"deletion_allowed": True})
        self._pedir("DELETE", ruta)


class _NoEsta(Exception):
    """404 de Vault. Interna: nunca sale de este módulo."""


def _texto(exc: urllib.error.HTTPError) -> str:
    """Lo que Vault dijo, si dijo algo que se pueda leer."""
    try:
        return exc.read().decode("utf-8", "replace")[:200]
    except Exception:  # noqa: BLE001 — el cuerpo ya consumido, o sin cuerpo
        return ""


def _tipo_de(pkcs8_der: bytes) -> str:
    """El nombre que transit le da a esta llave, o se rechaza antes de mandarla.

    Mandar un tipo que no coincide con la llave hace que Vault la acepte y falle
    después, al firmar, con un mensaje que no menciona el tamaño.
    """
    llave = serialization.load_der_private_key(pkcs8_der, password=None)
    if not isinstance(llave, rsa.RSAPrivateKey):
        raise SigningUnavailable(
            "el certificado no lleva una llave RSA, que es la única que firma "
            "XAdES-EPES"
        )
    tipo = _TIPOS_RSA.get(llave.key_size)
    if tipo is None:
        raise SigningUnavailable(f"una llave RSA de {llave.key_size} bits no la admite Vault")
    return tipo


def document_signer() -> VaultDocumentSigner:
    """El firmante que dice la configuración."""
    return VaultDocumentSigner(
        os.getenv("FE_VAULT_ADDR", "http://vault:8200"),
        os.getenv("FE_VAULT_TOKEN", ""),
    )
