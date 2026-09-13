"""
AES-256-GCM para la contraseña de ATV (T-602a, T-618).

`cryptography` ya estaba en el proyecto y sabe hacer esto; no entra ninguna
dependencia nueva.

**Por qué GCM y no CBC.** GCM autentica además de cifrar: si el valor guardado
se modificó, descifrar **falla** en vez de devolver basura. Y sobre todo, admite
**dato asociado** —texto que no se cifra pero que tiene que coincidir para poder
abrir—, y ahí van la compañía y el ambiente. Eso convierte «no copies filas
entre clientes» de una advertencia en una imposibilidad.

**El nonce va delante del cifrado y no se guarda aparte.** Son 12 bytes que no
son secretos pero que **no se pueden repetir con la misma llave**: repetir un
nonce en GCM no filtra el texto claro pero sí permite falsificar, que para una
credencial es igual de malo. Se sortea nuevo en cada cifrado y viaja pegado, así
que no hay forma de guardar uno sin el otro.

**El formato es base64url y no binario** porque la columna es `VARCHAR`: ver la
migración 011, donde está el porqué —el modelo y la migración tienen que decir
lo mismo sin un tipo que solo exista en MySQL—.
"""

from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.application.ports.secrets import SecretUnreadable

#: AES-256. Ni más ni menos: 16 y 24 también son llaves válidas de AES y dan
#: cifrado más débil sin que nada avise.
KEY_BYTES = 32

#: Los 12 bytes que recomienda el estándar para GCM. Con otro tamaño, GCM tiene
#: que derivarlo, y eso lo saca del camino probado sin ganar nada.
NONCE_BYTES = 12

#: Nombre de la variable, en un solo sitio para que el mensaje de error y el
#: compose no puedan desincronizarse.
ENV_KEY = "FE_CRYPTO_KEY"


class CryptoKeyMissing(RuntimeError):
    """El arranque no puede seguir sin la llave, y falla temprano a propósito.

    El otro momento posible para enterarse es el día que alguien guarda
    credenciales de Hacienda, que es tarde: para entonces el despliegue ya se
    dio por bueno.
    """


def load_key(value: str | None) -> bytes:
    """Los 32 bytes de `FE_CRYPTO_KEY`, o se cae."""
    if not value:
        raise CryptoKeyMissing(
            f"Falta {ENV_KEY}. Generala con: "
            'python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    try:
        # `+ "="` cubre los 43 caracteres que produce `token_urlsafe(32)`, que
        # van sin relleno. Python exige el relleno y sobra el de más.
        crudo = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as exc:
        raise CryptoKeyMissing(f"{ENV_KEY} no es base64url válido") from exc

    if len(crudo) != KEY_BYTES:
        raise CryptoKeyMissing(
            f"{ENV_KEY} mide {len(crudo)} bytes y tiene que medir {KEY_BYTES}. "
            'Generala con: python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    return crudo


def _dato_asociado(company_id: int, environment: str) -> bytes:
    """Lo que tiene que coincidir para poder abrir.

    Va como texto y no como bytes crudos del entero para que se pueda leer en un
    volcado de depuración: es información pública —qué compañía, qué ambiente—,
    y lo único que hace es atar el cifrado a su sitio.
    """
    return f"{company_id}:{environment}".encode("utf-8")


class AesGcmSecretBox:
    """Implementa `SecretBox` con AES-256-GCM y una llave del entorno."""

    def __init__(self, key: bytes) -> None:
        if len(key) != KEY_BYTES:
            raise CryptoKeyMissing(f"la llave mide {len(key)} bytes y no {KEY_BYTES}")
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: str, *, company_id: int, environment: str) -> str:
        nonce = os.urandom(NONCE_BYTES)
        sellado = self._aead.encrypt(
            nonce, plaintext.encode("utf-8"), _dato_asociado(company_id, environment)
        )
        return base64.urlsafe_b64encode(nonce + sellado).decode("ascii")

    def decrypt(self, sealed: str, *, company_id: int, environment: str) -> str:
        try:
            crudo = base64.urlsafe_b64decode(sealed + "=" * (-len(sealed) % 4))
        except (binascii.Error, ValueError) as exc:
            raise SecretUnreadable("el valor guardado no es base64url") from exc

        if len(crudo) <= NONCE_BYTES:
            # Sin nonce no hay nada que descifrar. Pasa con una fila truncada o
            # con una cadena vacía que alguien guardó creyendo que era un cifrado.
            raise SecretUnreadable("el valor guardado es más corto que su nonce")

        try:
            claro = self._aead.decrypt(
                crudo[:NONCE_BYTES],
                crudo[NONCE_BYTES:],
                _dato_asociado(company_id, environment),
            )
        except InvalidTag as exc:
            raise SecretUnreadable(
                "no abre con esta llave, esta compañía y este ambiente"
            ) from exc

        return claro.decode("utf-8")


def secret_box() -> AesGcmSecretBox:
    """La caja que dice el entorno. Se cae si la llave no está o no sirve."""
    return AesGcmSecretBox(load_key(os.getenv(ENV_KEY)))
