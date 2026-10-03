from sqlalchemy import CHAR, DATE, Column, Integer, Numeric, String, UniqueConstraint

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
    # Las otras señas de un cliente del extranjero (F7, RF-78, T-727): van en
    # el receptor de la factura de exportación en lugar de la ubicación del
    # país, que un extranjero no domiciliado no tiene. 300 es el largo del XSD.
    foreign_address = Column(String(300), nullable=True)
    register_date = Column(DATE, nullable=True)

    # ------------------------------------------- la exoneración (F7, T-717)
    #
    # **Son puntos de tarifa, no una tarifa** (RN-78): una línea al 13 % con
    # nueve puntos exonerados paga 4 %. No existe ninguna tarifa del 9 %, así
    # que guardar «0.04» en vez de «9» daría un comprobante que no cuadra
    # consigo mismo.
    #
    # Los siete campos son los que el XML pide y ninguno se deduce de otro. Van
    # en la fila del cliente y no en una tabla aparte porque el XSD lleva una
    # sola exoneración por línea: una segunda no tendría dónde ir.
    #
    # Todos en nulo es «este cliente no tiene exoneración», que es lo normal.
    # Los siete se llenan juntos o ninguno; lo custodia `fe_exemptions`.
    exo_document_type = Column(CHAR(2), nullable=True)
    exo_document_number = Column(String(40), nullable=True)
    exo_institution = Column(CHAR(2), nullable=True)
    exo_institution_other = Column(String(160), nullable=True)
    exo_article = Column(Integer, nullable=True)
    exo_subsection = Column(Integer, nullable=True)
    #: `DATE` y no `DATETIME` aunque el XML pida un `dateTime`: el documento de
    #: exoneración se emite un día, no a una hora —los ejemplos reales traen
    #: todos `T00:00:00`—. Guardar una hora inventada y después emitirla sería
    #: declararle a Hacienda una precisión que nadie tiene.
    exo_date = Column(DATE, nullable=True)
    #: Los **puntos** perdonados: 9 es nueve puntos, no el 9 %. `decimal 4,2`
    #: como el campo del XSD.
    exo_points = Column(Numeric(4, 2), nullable=True)

    # Únicos por compañía y no en toda la base: el mismo cliente puede comprar
    # en dos negocios distintos, y cada uno lo registra por su cuenta.
    __table_args__ = (
        UniqueConstraint("company_id", "identification", name="uq_clients_company_identification"),
        UniqueConstraint("company_id", "email", name="uq_clients_company_email"),
    )
