from sqlalchemy import Column, Integer, String, ForeignKey
from app.database.database import Base


class User(Base):
    __tablename__ = "users"

    id_user = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(50), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    id_person = Column(Integer, ForeignKey("persons.id_person"), nullable=False)
    # 'admin' gestiona inventario, usuarios y reportes; 'cajero' solo vende.
    # Las cuentas nuevas entran como cajero: el permiso se concede, no se hereda.
    role = Column(String(20), nullable=False, default="cajero")
