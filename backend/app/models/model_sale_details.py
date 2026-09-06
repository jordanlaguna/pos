from sqlalchemy import Column, ForeignKey, Integer, Numeric

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

    # `company_id` acá es redundante: ya se sabe por la venta. Se paga un INT
    # por fila a cambio de que el filtro automático cubra también las consultas
    # que entran por el detalle sin pasar por la cabecera —«¿en qué facturas
    # salió este producto?» no toca `sales` y sin la columna leería sin filtrar—.
