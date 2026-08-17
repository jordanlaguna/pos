from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class Settings(TenantMixin, Base):
    """Configuración del negocio. Una fila por compañía.

    Por qué una fila con JSON y no una columna por opción
    ------------------------------------------------------
    La configuración crece: hoy son moneda, impuesto y plantilla del documento;
    mañana serán los datos de facturación electrónica. Una columna por opción
    obliga a un ALTER TABLE —y a una migración coordinada con el frontend— cada
    vez que se agrega una casilla. Aquí el backend guarda y devuelve el objeto
    tal como se lo manda el POS, y quien conoce la forma es el frontend, que ya
    la valida antes de escribir.

    El precio de esa decisión es que no se puede filtrar por un campo con SQL.
    Para una fila que se lee entera y se escribe entera, no se pierde nada.

    El logo va aparte y no dentro del JSON: es lo único voluminoso, y así una
    lectura de configuración no arrastra 300 KB de imagen cuando solo se
    necesita el símbolo de la moneda.
    """

    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    data = Column(Text, nullable=False, default="{}")

    # Text(4294967295) es LONGTEXT en MySQL. Un TEXT normal son 64 KB y un PNG
    # de 250 KB en base64 ocupa ~340 KB: se truncaría en silencio.
    logo_mime = Column(String(60), nullable=True)
    logo_data = Column(Text(4294967295), nullable=True)

    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(Integer, nullable=True)

    # Lo que impide que aparezcan dos filas para la misma compañía. Antes el
    # invariante era «siempre id = 1» y lo sostenía el código; ahora lo sostiene
    # la base, que es donde los invariantes no se olvidan.
    __table_args__ = (UniqueConstraint("company_id", name="uq_settings_company"),)
