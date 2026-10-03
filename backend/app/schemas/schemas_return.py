from pydantic import BaseModel
import datetime

from app.schemas.schemas_einvoice import EInvoiceOut


class ReturnItemInput(BaseModel):
    id_product: int
    quantity: int


class ReturnCreate(BaseModel):
    sale_id: int
    user_id: int
    reason: str
    items: list[ReturnItemInput]
    # Anular el comprobante en vez de devolver mercadería (RN-89). Exige la
    # venta entera y sin devoluciones previas.
    annul: bool = False


class ReturnItemResponse(BaseModel):
    id_product: int
    name: str
    quantity: int
    price: float
    subtotal: float
    # La tarifa con que se cobró la línea y lo reembolsado de impuesto. Es lo
    # que desglosa la nota de crédito impresa (RF-21), igual que la factura.
    tax_rate: float | None = None
    tax_amount: float | None = None
    # Los de la línea de la venta: la nota repite con qué se vendió (RN-86).
    cabys_code: str | None = None
    unit_of_measure: str | None = None


class ReturnResponse(BaseModel):
    id: int
    sale_id: int
    sale_number: str
    user_id: int
    user_name: str | None = None
    created_at: datetime.datetime
    reason: str
    # El desglose de lo reembolsado (T-509b). En nulo para las devoluciones
    # anteriores a la migración 006, que solo guardaron el total.
    subtotal: float | None = None
    tax: float | None = None
    total: float
    # True cuando ya no queda ninguna unidad de la venta por devolver.
    is_full: bool
    items: list[ReturnItemResponse] = []
    # La nota de crédito (RN-89): '03' y el motivo, o nulos si la venta no fue
    # comprobante. Y lo que la nota impresa dice del original.
    document_type: str | None = None
    reference_code: str | None = None
    sale_document_type: str | None = None
    sale_created_at: datetime.datetime | None = None
    sale_client_id: int | None = None
    sale_payment_method: str | None = None
    # La nota de crédito numerada, y la clave del comprobante que modifica: es
    # como se referencia (T-705). Nula en una venta de antes de numerar.
    einvoice: EInvoiceOut | None = None
    sale_clave: str | None = None

    model_config = {"from_attributes": True}


class ReturnCreateSuccess(BaseModel):
    message: str
    id_return: int
    total: float
    # Si hubo nota de crédito: la pantalla lleva a imprimirla.
    document_type: str | None = None
