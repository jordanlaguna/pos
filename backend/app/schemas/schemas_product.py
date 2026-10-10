from pydantic import BaseModel
import datetime

class ProductRegister(BaseModel):
    # Product attributes
    name: str
    description: str
    price: float
    stock: int
    barcode: str
    created_at: datetime.datetime
    category_id: int

    # --- F5: el impuesto es del producto, no del negocio (RN-9) -------------
    #
    # `tax_rate` entre 0 y 1: el 13 % es 0.13. En NULL significa «la tasa
    # configurada», que es lo que tienen los productos anteriores a F5 y los que
    # nadie ha clasificado todavía.
    cabys_code: str | None = None
    tax_rate: float | None = None
    unit_of_measure: str | None = None

    # --- F7: el código de tarifa de Hacienda (RN-76) ------------------------
    #
    # No es el porcentaje: hay once códigos para nueve porcentajes y el 0 % con
    # derecho a crédito (`01`) y el 0 % sin derecho (`11`) son el mismo número.
    # Cuando viene, **manda sobre `tax_rate`**: la tarifa se deriva de él.
    tax_code: str | None = None

    # --- F7: la partida arancelaria (RF-78, T-727) ---------------------------
    #
    # Doce dígitos. Solo la necesita una mercancía el día que se le venda a un
    # cliente del extranjero; vacía es «no tiene».
    tariff_heading: str | None = None

    # --- F15: cuánto es poco para este producto (RN-101) ---------------------
    #
    # Nulo usa el mínimo general de Configuración.
    min_stock: int | None = None

class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None
    stock: int | None = None
    barcode: str | None = None
    created_at: datetime.datetime | None = None
    category_id: int | None = None

    # --- F5: el impuesto es del producto, no del negocio (RN-9) -------------
    #
    # `tax_rate` entre 0 y 1: el 13 % es 0.13. En NULL significa «la tasa
    # configurada», que es lo que tienen los productos anteriores a F5 y los que
    # nadie ha clasificado todavía.
    cabys_code: str | None = None
    tax_rate: float | None = None
    unit_of_measure: str | None = None

    # --- F7: el código de tarifa de Hacienda (RN-76) ------------------------
    #
    # No es el porcentaje: hay once códigos para nueve porcentajes y el 0 % con
    # derecho a crédito (`01`) y el 0 % sin derecho (`11`) son el mismo número.
    # Cuando viene, **manda sobre `tax_rate`**: la tarifa se deriva de él.
    tax_code: str | None = None

    # --- F7: la partida arancelaria (RF-78, T-727). Vacía la quita. ---------
    tariff_heading: str | None = None

    # --- F15: el mínimo propio (RN-101). Nulo lo quita y vuelve al general. --
    min_stock: int | None = None

class ProductResponse(BaseModel):
    id_product: int
    name: str
    description: str
    price: float
    stock: int
    barcode: str
    created_at: datetime.datetime
    category_id: int

    # --- F5: el impuesto es del producto, no del negocio (RN-9) -------------
    #
    # `tax_rate` entre 0 y 1: el 13 % es 0.13. En NULL significa «la tasa
    # configurada», que es lo que tienen los productos anteriores a F5 y los que
    # nadie ha clasificado todavía.
    cabys_code: str | None = None
    tax_rate: float | None = None
    unit_of_measure: str | None = None

    # --- F7: el código de tarifa de Hacienda (RN-76) ------------------------
    #
    # No es el porcentaje: hay once códigos para nueve porcentajes y el 0 % con
    # derecho a crédito (`01`) y el 0 % sin derecho (`11`) son el mismo número.
    # Cuando viene, **manda sobre `tax_rate`**: la tarifa se deriva de él.
    tax_code: str | None = None

    # --- F7: la partida arancelaria (RF-78, T-727) ---------------------------
    tariff_heading: str | None = None

    # --- F15: el mínimo propio (RN-101); nulo usa el general -----------------
    min_stock: int | None = None

    # --- F10: lo que cuesta, no lo que vale (RN-54) -------------------------
    #
    # Promedio ponderado móvil de las compras. Solo de lectura: lo escribe
    # `RegisterStockEntry` al recibir mercadería y no hay forma de fijarlo a
    # mano, porque un costo escrito a dedo deja de ser el promedio de nada. En
    # cero significa «no se sabe todavía», que es lo que tienen los productos
    # anteriores a F10.
    cost: float = 0

    model_config = {
        "from_attributes": True
    }

class ProductUpdateResponse(BaseModel):
    message: str
    id_product: int

class CabysAssignment(BaseModel):
    """Asignación de CABYS en lote (RF-20).

    El código y la tarifa van juntos y los dos son obligatorios: asignar un
    CABYS **es** copiar su tarifa (RN-11), y mandar uno sin la otra dejaría al
    producto diciendo que es harina de arroz y cobrando otra cosa.
    """

    product_ids: list[int]
    cabys_code: str
    #: Entre 0 y 1, como en todo el sistema. El 13 % es 0.13.
    tax_rate: float

class CabysAssignmentResult(BaseModel):
    message: str
    #: Cuántos productos quedaron clasificados. Es todos o ninguno.
    updated: int
class ProdcutRegisterSuccess(BaseModel):
    message: str
    id_product: int

    model_config = {
        "from_attributes": True
    }