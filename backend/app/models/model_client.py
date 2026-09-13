from sqlalchemy import DATE, Column, Integer, String, UniqueConstraint

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class Client(TenantMixin, Base):
    __tablename__ = "clients"

    id_client = Column(Integer, primary_key=True, index=True)
    identification = Column(String(100), nullable=False)
    # El tipo que el XML exige para el receptor (F6, T-617): '01' física, '02'
    # jurídica, '03' DIMEX, '04' NITE. Estaba en spec §5.4 desde el principio y
    # nunca tuvo columna. NULL es «no se sabe», que es lo que queda cuando la
    # longitud de la cédula no alcanza para deducirlo.
    identification_type = Column(String(2), nullable=True)
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
