"""
Numerar un comprobante: el consecutivo y la clave (T-704, T-705).

No es un caso de uso que se llame solo sino una pieza de tres: la venta, la
devolución que lleva nota de crédito y la nota por monto. Las tres lo usan
igual y en dos tiempos:

1. **`prepare()`, antes de la transacción.** Lee el emisor y dice que no si no
   se puede numerar. Todo lo que puede decir que no, lo dice antes de tocar
   existencias (register_sale.py, paso 1).
2. **`number(...)`, adentro.** Bloquea la serie, toma el número y guarda el
   comprobante — **en la misma transacción que el documento** (plan §7.2). Una
   venta que falla después por stock revierte también el número, y la serie no
   queda con un hueco. Es el defecto 1 otra vez, del lado del contador.

La **situación** es siempre la normal por ahora. La contingencia es un modo del
negocio que se decide por el estado de las transmisiones recientes (RN-43), y
todavía no se transmite nada: emitir en contingencia sin haber observado una
falla es causa de rechazo, así que no se adivina.
"""

from __future__ import annotations

from datetime import datetime

from app.application.ports.numbering import (
    DocumentNumbering,
    Issuer,
    IssuerRepository,
    NumberedDocument,
    SecurityCodes,
)
from app.domain.errors import InvalidKeyPart, IssuerIdentificationRequired
from app.domain.fe_key import SITUATION_NORMAL, build_clave, consecutive, issuer_digits, next_sequence
from app.domain.office import BranchCode, TerminalCode

#: De dónde nace un comprobante. Son los tres flujos que numeran hoy.
SOURCE_SALE = "sale"
SOURCE_RETURN = "return"
SOURCE_NOTE = "note"


class NumberDocument:
    def __init__(
        self,
        *,
        issuer: IssuerRepository,
        numbering: DocumentNumbering,
        security_codes: SecurityCodes,
    ) -> None:
        self._issuer = issuer
        self._numbering = numbering
        self._codes = security_codes

    def prepare(self) -> Issuer:
        """El emisor, o `IssuerIdentificationRequired` si no se puede numerar.

        La cédula se valida acá entera —no solo que exista— para que una mal
        cargada diga que no antes de la transacción y no a mitad de ella.
        """
        emisor = self._issuer.issuer()
        if not emisor.identification or not emisor.identification.strip():
            raise IssuerIdentificationRequired("missing")
        try:
            issuer_digits(emisor.identification)
        except InvalidKeyPart:
            raise IssuerIdentificationRequired("invalid") from None
        return emisor

    def number(
        self,
        issuer: Issuer,
        *,
        source_type: str,
        source_id: int,
        document_type: str,
        issued_at: datetime,
    ) -> NumberedDocument:
        oficina = self._numbering.office()
        ultima = self._numbering.last_sequence(
            document_type=document_type, environment=issuer.environment
        )
        secuencia = next_sequence(ultima)
        numero = consecutive(
            BranchCode(oficina.branch_code),
            TerminalCode(oficina.terminal_code),
            document_type,
            secuencia,
        )
        clave = build_clave(
            issued_on=issued_at.date(),
            issuer_identification=issuer.identification or "",
            consecutive=numero,
            situation=SITUATION_NORMAL,
            security_code=self._codes.new(),
        )
        documento = NumberedDocument(
            source_type=source_type,
            source_id=source_id,
            document_type=document_type,
            environment=issuer.environment,
            sequence=secuencia,
            consecutive=numero,
            clave=clave,
            situation=SITUATION_NORMAL,
            economic_activity=issuer.economic_activity or None,
            issued_at=issued_at,
        )
        self._numbering.save_sequence(
            document_type=document_type, environment=issuer.environment, value=secuencia
        )
        self._numbering.record(documento)
        return documento
