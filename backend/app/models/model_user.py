from sqlalchemy import Column, ForeignKey, Integer, String

from app.database.database import Base


class User(Base):
    """La identidad de una persona: un correo y una contraseña.

    No hereda `TenantMixin` y no tiene `company_id`. Una cuenta puede entrar a
    varias compañías —el contador que atiende tres locales— y preguntar «a cuál
    pertenece» no tendría respuesta (RN-3). La pertenencia vive en
    `user_companies`, con su propio rol por compañía.

    El `role` que había acá desapareció por eso mismo: la misma persona puede
    ser administradora en su negocio y cajera en el de un socio, así que el rol
    no es una propiedad de la persona sino de la membresía.
    """

    __tablename__ = "users"

    id_user = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(50), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    id_person = Column(Integer, ForeignKey("persons.id_person"), nullable=False)

    # Idioma preferido. NULL es «lo que diga la compañía», y es distinto de
    # haber elegido español: si mañana la compañía cambia a portugués, quien
    # nunca tocó el ajuste se va con ella y quien eligió se queda (RN-28).
    locale = Column(String(10), nullable=True)
