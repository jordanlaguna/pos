from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class Product(TenantMixin, Base):
    __tablename__ = "products"

    id_product = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    price = Column(Numeric(10, 2), nullable=False)
    stock = Column(Integer, nullable=False)
    # index=True: el escáner busca por este campo en cada lectura.
    barcode = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)

    # Antes solo tenía índice. Ahora es único POR COMPAÑÍA, que es lo que el
    # escáner necesita —una lectura, un producto— sin impedir que dos negocios
    # vendan el mismo artículo. Los nulos no chocan entre sí en MySQL, así que
    # los productos sin código de barras siguen conviviendo.
    __table_args__ = (
        UniqueConstraint("company_id", "barcode", name="uq_products_company_barcode"),
    )
