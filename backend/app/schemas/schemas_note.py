from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.schemas_einvoice import EInvoiceOut


class NoteLineInput(BaseModel):
    id_product: int
    #: Lo que se cobra o se devuelve por esa línea, **con impuesto**.
    amount: float


class NoteCreate(BaseModel):
    """Una nota por monto sobre un comprobante (RF-77, T-726).

    Quién la emite sale del token, no del cuerpo: una nota mueve plata sin
    mercadería, y no puede quedar a nombre de otro.
    """

    sale_id: int
    #: '02' nota de débito, '03' nota de crédito.
    document_type: str
    #: El motivo de Hacienda. Hoy solo '02', corrige monto.
    reference_code: str = "02"
    reason: str = Field(default="", max_length=255)
    items: list[NoteLineInput] = []
    #: Cómo se cobra la ND. La NC no lo lleva: sale de la gaveta.
    payment_method: str | None = None


class NoteCreateSuccess(BaseModel):
    message: str
    id_note: int
    document_type: str
    total: float


class NoteItemResponse(BaseModel):
    id_product: int
    name: str
    subtotal: float
    tax_rate: float
    tax_amount: float
    tax_code: str | None = None
    cabys_code: str | None = None
    unit_of_measure: str | None = None


class NoteResponse(BaseModel):
    id: int
    sale_id: int
    sale_number: str
    user_id: int
    user_name: str | None = None
    created_at: datetime
    document_type: str
    reference_code: str
    reason: str
    payment_method: str | None = None
    subtotal: float
    tax: float
    total: float
    items: list[NoteItemResponse] = []
    # Lo que la nota impresa dice del original (RN-89).
    sale_document_type: str | None = None
    sale_created_at: datetime | None = None
    sale_client_id: int | None = None
    # La nota numerada y la clave del original, como en la devolución (T-705).
    einvoice: EInvoiceOut | None = None
    sale_clave: str | None = None
