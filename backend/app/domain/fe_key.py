"""
El consecutivo de 20 dígitos y la clave de 50 (nota 3 del anexo; T-704, T-705).

**El consecutivo** es la numeración del comprobante:

    sucursal (3) + terminal (5) + tipo (2) + secuencia (10)
    001            00001          01         0001819201

**La clave** es su identificador ante Hacienda, y lo contiene:

    país (3) + día (2) + mes (2) + año (2) + emisor (12) + consecutivo (20)
    + situación (1) + código de seguridad (8)

Todo es aritmética y no necesita red: se arma **al vender**, porque se imprime
y se entrega en el mostrador (RN-43). Lo que puede esperar al momento de
transmitir es la firma, no esto.

Ninguna pieza la escribe una persona —las pone el sistema o soporte—, así que
un valor que no cabe es un error de programación o un dato mal cargado, y se
rechaza con `InvalidKeyPart` en vez de recortarse: recortar en silencio le
cambia el número a un comprobante.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from .errors import InvalidKeyPart
from .office import BranchCode, TerminalCode

#: Costa Rica. La clave empieza siempre así.
COUNTRY_CODE: Final = "506"

SEQUENCE_DIGITS: Final = 10
#: La secuencia más alta que cabe. Al llegar, se vuelve a 1 (nota 3, inciso d).
MAX_SEQUENCE: Final = 10**SEQUENCE_DIGITS - 1
CONSECUTIVE_LENGTH: Final = 20
ISSUER_DIGITS: Final = 12
SECURITY_CODE_DIGITS: Final = 8

#: La posición 42 de la clave (nota 3, inciso g).
SITUATION_NORMAL: Final = "1"
SITUATION_CONTINGENCY: Final = "2"
SITUATION_NO_INTERNET: Final = "3"
SITUATIONS: Final = (SITUATION_NORMAL, SITUATION_CONTINGENCY, SITUATION_NO_INTERNET)

#: Los que llevan serie propia (nota 3, inciso c). Del 05 al 07 son los mensajes
#: de confirmación del receptor, que también se numeran.
SERIES_TYPES: Final = ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10")


def _entero(value: object) -> bool:
    # Un booleano es un `int` en Python, y `True` sería la secuencia 1.
    return isinstance(value, int) and not isinstance(value, bool)


def next_sequence(last: object) -> int:
    """La secuencia que sigue a `last`, que es la última emitida (0 si ninguna).

    Al tope se vuelve a empezar desde 1, que es lo que el anexo permite. No
    pasa: son diez mil millones de comprobantes por caja y por tipo.
    """
    if not _entero(last) or last < 0 or last > MAX_SEQUENCE:
        raise InvalidKeyPart("sequence", last)
    return 1 if last == MAX_SEQUENCE else last + 1


def consecutive(
    branch: BranchCode, terminal: TerminalCode, document_type: str, sequence: int
) -> str:
    """Los 20 dígitos. Los códigos de oficina ya vienen con sus ceros (RN-15)."""
    if document_type not in SERIES_TYPES:
        raise InvalidKeyPart("document_type", document_type)
    if not _entero(sequence) or not 1 <= sequence <= MAX_SEQUENCE:
        raise InvalidKeyPart("sequence", sequence)
    return f"{branch}{terminal}{document_type}{sequence:0{SEQUENCE_DIGITS}d}"


def issuer_digits(identification: object) -> str:
    """La cédula del emisor completada a doce con ceros a la izquierda (nota 4.1).

    La nota lo dice por tipo —tres ceros a la física, dos a la jurídica, uno al
    DIMEX de once— y las cuatro reglas son la misma: llegar a doce. Se aceptan
    guiones y espacios porque así se escribe una cédula; letras, no.
    """
    if not isinstance(identification, str):
        raise InvalidKeyPart("issuer", identification)
    digitos = "".join(c for c in identification if c not in "- \t")
    if not digitos or not digitos.isascii() or not digitos.isdigit() or len(digitos) > ISSUER_DIGITS:
        raise InvalidKeyPart("issuer", identification)
    return digitos.zfill(ISSUER_DIGITS)


def build_clave(
    *,
    issued_on: date,
    issuer_identification: str,
    consecutive: str,
    situation: str,
    security_code: str,
) -> str:
    """La clave de 50 dígitos.

    `issued_on` es el día de la emisión **en Costa Rica**: tiene que coincidir con
    la `FechaEmision` del XML, y el backend sella con la hora local del
    contenedor, que corre con `TZ=America/Costa_Rica`.
    """
    if not isinstance(consecutive, str) or len(consecutive) != CONSECUTIVE_LENGTH or not (
        consecutive.isascii() and consecutive.isdigit()
    ):
        raise InvalidKeyPart("consecutive", consecutive)
    if situation not in SITUATIONS:
        raise InvalidKeyPart("situation", situation)
    if not isinstance(security_code, str) or len(security_code) != SECURITY_CODE_DIGITS or not (
        security_code.isascii() and security_code.isdigit()
    ):
        raise InvalidKeyPart("security_code", security_code)

    return (
        f"{COUNTRY_CODE}{issued_on:%d%m%y}{issuer_digits(issuer_identification)}"
        f"{consecutive}{situation}{security_code}"
    )
