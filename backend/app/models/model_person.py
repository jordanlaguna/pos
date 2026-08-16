from sqlalchemy import Column, Integer, String
from app.database.database import Base

class Person(Base):
    __tablename__ = "persons"

    id_person = Column(Integer, primary_key=True, index=True, autoincrement=True)
    birth_date = Column(String(50), nullable=True)
    identification = Column(String(100), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    lastName = Column(String(100), nullable=False)
    secondName = Column(String(100), nullable=False)
    telephone = Column(String(100), nullable=True)