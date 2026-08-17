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

    # `company_id` acá es redundante: ya se sabe por la venta. Se paga un INT
    # por fila a cambio de que el filtro automático cubra también las consultas
    # que entran por el detalle sin pasar por la cabecera —«¿en qué facturas
    # salió este producto?» no toca `sales` y sin la columna leería sin filtrar—.
