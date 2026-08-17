from sqlalchemy import DATE, Column, Integer, String, UniqueConstraint

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class Client(TenantMixin, Base):
    __tablename__ = "clients"

    id_client = Column(Integer, primary_key=True, index=True)
    identification = Column(String(100), nullable=False)
    name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    second_name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False)
    telephone = Column(Integer, nullable=True)
    address = Column(String(100), nullable=True)
    register_date = Column(DATE, nullable=True)

    # Únicos por compañía y no en toda la base: el mismo cliente puede comprar
    # en dos negocios distintos, y cada uno lo registra por su cuenta.
    __table_args__ = (
        UniqueConstraint("company_id", "identification", name="uq_clients_company_identification"),
        UniqueConstraint("company_id", "email", name="uq_clients_company_email"),
    )
