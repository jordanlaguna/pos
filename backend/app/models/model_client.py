from sqlalchemy import Column, Integer, String,DATE
from app.database.database import Base

class Client(Base):
    __tablename__ = "clients"

    id_client = Column(Integer, primary_key=True, index=True)
    identification = Column(String(100), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    second_name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    telephone = Column(Integer, nullable=True)
    address = Column(String(100), nullable=True)
    register_date = Column(DATE, nullable=True)