from app.database.database import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric


class Product(Base):
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
