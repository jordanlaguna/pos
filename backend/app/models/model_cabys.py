"""La caché del catálogo CABYS de Hacienda (T-501).

**Global, no por compañía**, y por eso NO hereda `TenantMixin`: el catálogo es
del país, es el mismo para todos los clientes, y cachearlo por compañía sería
guardar veinte copias de la misma fila y pedirle veinte veces lo mismo a
Hacienda. Es la segunda tabla global del sistema, después de `plans`.

Que no herede el mixin tiene una consecuencia que conviene saber: sus consultas
**no llevan filtro automático** y por eso funcionan desde una sesión sin
compañía. Es correcto acá y hay que mirarlo dos veces en cualquier tabla nueva,
porque es exactamente la puerta por la que se filtran datos entre clientes. Acá
no hay dato de nadie: son códigos publicados por Hacienda.

Se llena con lo que se va usando y no con el catálogo entero —son unos veinte
mil y un POS usa unas decenas—. Al asignarle un código a un producto se copia
acá, y eso es lo que hace que **facturar no dependa de que Hacienda esté
arriba** (RNF-4).
"""

from sqlalchemy import CHAR, Column, DateTime, Numeric, String

from app.database.database import Base


class CabysCache(Base):
    __tablename__ = "cabys_cache"

    # El código ES la llave: viene de Hacienda, es único y no hay id técnico que
    # agregue nada. Trece dígitos con ceros a la izquierda, así que CHAR.
    code = Column(CHAR(13), primary_key=True)
    description = Column(String(500), nullable=False)

    # La tarifa oficial del código. Seis decimales, como toda tasa del sistema.
    tax_rate = Column(Numeric(7, 6), nullable=False)

    # Cuándo se leyó de Hacienda. Es lo que permite decirle a quien busca sin
    # internet desde cuándo es lo que está viendo (RNF-4).
    updated_at = Column(DateTime, nullable=False)
