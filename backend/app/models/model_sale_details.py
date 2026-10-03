from sqlalchemy import CHAR, Column, ForeignKey, Integer, Numeric, String

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class SaleDetail(TenantMixin, Base):
    __tablename__ = "sale_details"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id_product"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)

    # La tarifa CONGELADA al cobrar, no la que tenga el producto hoy (RN-12).
    # NULL es «venta anterior a F5»: esas llevan una sola tarifa y se reconstruye
    # del encabezado con `TaxRate.of_sale`, que para ellas es exacta. Con tarifas
    # mezcladas ese cociente sería un promedio y una devolución parcial
    # reembolsaría de más o de menos.
    #
    # Seis decimales porque una tasa no es un monto: con dos se perdería el
    # 2,5 % y cualquier tarifa fina del catálogo de Hacienda.
    tax_rate = Column(Numeric(7, 6), nullable=True)

    # Redundante —se puede recalcular— y se guarda igual: es lo que se cobró de
    # verdad, con su redondeo, y una factura tiene que reimprimirse igual dentro
    # de cinco años aunque cambie cómo se redondea.
    tax_amount = Column(Numeric(10, 2), nullable=True)

    # El código de tarifa de Hacienda, congelado igual que la tarifa y por lo
    # mismo (F7, RN-76). Y con una razón más: **del porcentaje no se puede
    # volver al código**. Una línea al 0 % pudo ser una venta a la CCSS con
    # derecho a crédito pleno (`01`) o un bien no sujeto sin ninguno (`11`); si
    # no se guarda el código, la nota de crédito de dentro de un año tiene que
    # adivinar cuál era.
    #
    # NULL es «anterior a F7» o «el producto no estaba clasificado».
    tax_code = Column(CHAR(2), nullable=True)

    # El CABYS y la unidad con que se vendió, congelados por lo mismo (T-731,
    # RN-86): el comprobante los imprime por línea, y el producto puede cambiar
    # de CABYS después —el dueño lo corrige, Hacienda actualiza el catálogo—.
    # NULL es «anterior a la migración 016» o «el producto no tenía CABYS».
    cabys_code = Column(CHAR(13), nullable=True)
    unit_of_measure = Column(String(15), nullable=True)

    # La partida arancelaria con que se exportó (T-727), congelada por lo mismo.
    # Solo la lleva la línea de una factura de exportación; en las demás es NULL.
    tariff_heading = Column(CHAR(12), nullable=True)

    # El costo promedio del producto AL MOMENTO DE VENDERSE (RN-63), congelado
    # igual que la tarifa y por la misma razón. Vender hoy con costo ₡110 y
    # comprar mañana a ₡150 no cambia el costo de lo que ya salió; leerlo de
    # `products.cost` al armar el asiento reescribiría la utilidad del mes pasado
    # cada vez que llega una factura del proveedor.
    #
    # NULL —y no 0— en lo anterior a F11 y en el producto que no tiene costo: 0
    # diría «costó cero», que es falso. NULL dice «no se sabe», y una línea sin
    # costo simplemente no asienta el par costo / inventario.
    unit_cost = Column(Numeric(12, 2), nullable=True)

    # `company_id` acá es redundante: ya se sabe por la venta. Se paga un INT
    # por fila a cambio de que el filtro automático cubra también las consultas
    # que entran por el detalle sin pasar por la cabecera —«¿en qué facturas
    # salió este producto?» no toca `sales` y sin la columna leería sin filtrar—.
