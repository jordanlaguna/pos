from pydantic import BaseModel
import datetime

from app.schemas.schemas_einvoice import EInvoiceOut


class ProductSale(BaseModel):
    id_product: int
    # `stock` es la CANTIDAD vendida, no el inventario. El nombre viene del
    # cliente WinForms original y se conserva para no romper compatibilidad.
    stock: int


class SaleRegister(BaseModel):
    # Opcional desde T-706: sin él, el servidor lo pone con su reloj.
    sale_number: str | None = None
    # Opcional: las ventas de contado no llevan cliente asociado.
    client_id: int | None = None
    user_id: int
    total: float
    subtotal: float
    tax: float
    payment_method: str
    cash_received: float
    change_given: float
    # Se acepta por compatibilidad con el cliente WinForms, pero se IGNORA: la
    # hora de la venta la sella el servidor. Ver crud_sale.create_sale().
    created_at: datetime.datetime | None = None
    products: list[ProductSale]
    # '01' factura o '04' tiquete (RN-85). Opcional: sin él sale el que sugiere
    # el receptor, y con la facturación electrónica apagada se ignora. Es texto
    # y no un `Literal` para que un valor malo llegue al dominio y vuelva como
    # `invalid_sale_document_type`, no como un 422 sin código.
    document_type: str | None = None


class SalesList(BaseModel):
    id: int
    sale_number: str
    client_id: int | None = None
    user_id: int
    total: float
    subtotal: float
    tax: float
    payment_method: str
    cash_received: float
    change_given: float
    created_at: datetime.datetime
    # El comprobante que se emitió (RN-85). Nulo sin facturación electrónica.
    document_type: str | None = None
    # En qué va ante Hacienda (RN-39): numbered, signed, sent, accepted,
    # rejected, retrying, stopped. Nulo si la venta no tiene comprobante.
    einvoice_status: str | None = None

    model_config = {"from_attributes": True}


class SaleItem(BaseModel):
    id_product: int
    name: str
    quantity: int
    price: float
    subtotal: float

    # Lo que se cobró de impuesto en ESTA línea, con la tarifa que se le congeló
    # (RN-12). Es lo que desglosa el documento cuando la venta mezcla tarifas
    # (RF-21). En nulo para las ventas anteriores a la migración 006.
    tax_rate: float | None = None
    tax_amount: float | None = None

    # El código de tarifa de Hacienda con el que se cobró (F7, RN-76). Va acá y
    # no se recalcula porque **del porcentaje no se vuelve al código**: un 0 %
    # pudo ser una venta a la CCSS con derecho a crédito pleno o un bien no
    # sujeto sin ninguno. En nulo para lo anterior a F7.
    tax_code: str | None = None

    # El CABYS y la unidad con que se vendió (F7, T-731, RN-86), congelados en
    # la línea: el comprobante los imprime y el producto puede cambiarlos. En
    # nulo para lo anterior a la migración 016.
    cabys_code: str | None = None
    unit_of_measure: str | None = None
    #: La partida arancelaria con que se exportó (T-727). Solo en la FEE.
    tariff_heading: str | None = None


class SaleDetailResponse(SalesList):
    """Venta con sus líneas. La necesitan la factura y las devoluciones."""

    client_name: str | None = None
    user_name: str | None = None
    returned: bool = False
    items: list[SaleItem] = []
    # El comprobante numerado (T-705). Nulo sin facturación electrónica, o en
    # una venta de antes: esa se imprime «pendiente de emisión».
    einvoice: EInvoiceOut | None = None


class SaleRegisterSuccess(BaseModel):
    message: str
    id_sale: int

    model_config = {"from_attributes": True}
