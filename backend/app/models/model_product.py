from sqlalchemy import (
    CHAR,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class Product(TenantMixin, Base):
    __tablename__ = "products"

    id_product = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    price = Column(Numeric(10, 2), nullable=False)
    stock = Column(Integer, nullable=False)
    # `index=True` es redundante —`uq_products_company_barcode` ya responde
    # `WHERE company_id = ? AND barcode = ?` por su prefijo izquierdo, y toda
    # lectura del escáner lleva la compañía porque se la pone el filtro de
    # `tenancy.py`— y se queda igual: **las bases desplegadas tienen ese índice**
    # (`ix_products_barcode`, creado por `create_all` al nacer la tabla) y
    # quitarlo del modelo dejaría a una instalación nueva con un esquema distinto
    # del de las que ya corren. Igualar por el otro lado sería un DROP INDEX en
    # producción, que se decidió no hacer (T-915, 2026-09-05).
    barcode = Column(String(100), nullable=True, index=True)

    # El código del catálogo de Hacienda (RF-17). CHAR y no número: tiene ceros
    # a la izquierda y no se hace aritmética con él.
    cabys_code = Column(CHAR(13), nullable=True)

    # La tarifa de ESTE producto (RN-9). NULL significa «la configurada del
    # negocio», que es lo que se venía aplicando a todo: por eso la migración no
    # rellena nada y ningún precio cambia. La ficha propone la configurada al
    # crear un producto, que es lo que RN-9 llama «valor por omisión».
    tax_rate = Column(Numeric(7, 6), nullable=True)

    # La pide Hacienda en cada línea del comprobante (F6/F7). 'Unid' es el
    # código de «unidad», que es lo que vende un punto de venta salvo aviso.
    #
    # `server_default` y no `default`: el segundo es del lado de Python y **no
    # emite `DEFAULT` en el DDL**, así que `create_all` habría creado la columna
    # sin valor por omisión mientras la migración sí se lo pone. Es la forma que
    # tomó el defecto 19 —el mismo código sobre dos esquemas distintos— y acá se
    # habría colado por la puerta de al lado, porque la prueba de paridad compara
    # índices y todavía no compara valores por omisión (T-919).
    unit_of_measure = Column(String(15), nullable=False, server_default="Unid")

    created_at = Column(DateTime, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)

    # Antes solo tenía índice. Ahora es único POR COMPAÑÍA, que es lo que el
    # escáner necesita —una lectura, un producto— sin impedir que dos negocios
    # vendan el mismo artículo. Los nulos no chocan entre sí en MySQL, así que
    # los productos sin código de barras siguen conviviendo.
    # `idx_products_cabys` sostiene la asignación en lote (RF-20) y la pregunta
    # de «qué falta por clasificar». Lleva la compañía adelante porque toda
    # consulta de negocio la lleva: sin ella el índice no se usaría.
    __table_args__ = (
        UniqueConstraint("company_id", "barcode", name="uq_products_company_barcode"),
        Index("idx_products_cabys", "company_id", "cabys_code"),
    )
