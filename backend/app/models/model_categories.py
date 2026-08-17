from sqlalchemy import Column, Integer, String, UniqueConstraint

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class Category(TenantMixin, Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)

    # El nombre era único en toda la base, y eso impedía que dos compañías
    # tuvieran las dos una categoría «Bebidas».
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_categories_company_name"),)
