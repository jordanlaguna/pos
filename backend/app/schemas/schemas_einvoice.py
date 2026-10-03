from pydantic import BaseModel


class EInvoiceOut(BaseModel):
    """El comprobante numerado de una venta, una devolución o una nota (T-705).

    Es el contrato que lee `FiscalBlock.svelte` —`EmittedDocument` en el POS—, y
    es el mismo en los tres detalles.
    """

    #: Los 50 dígitos. Se imprime y se entrega en el mostrador (RN-43).
    clave: str
    #: Los 20: sucursal, caja, tipo y secuencia. Es el número del documento.
    consecutive: str
    #: `sandbox` o `production`. Lo de pruebas no tiene efecto fiscal (RN-17).
    environment: str
    #: La actividad con que se declaró, que puede no ser la configurada hoy.
    economic_activity: str | None = None
    #: 1 normal, 2 contingencia, 3 sin internet.
    situation: str
