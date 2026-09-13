"""Factura electrónica: credenciales y consecutivo (F6, T-601).

Dos tablas, y las dos con una llave primaria compuesta que no es un detalle
técnico sino la regla:

* `fe_credentials` lleva `(company_id, environment)` porque Hacienda emite las
  credenciales por separado para pruebas y para producción. Con `company_id` a
  secas, «pasar a producción» significaba borrar lo de pruebas y quedarse sin
  poder volver, y un cliente en integración tiene los dos a la vez (RN-33).
* `fe_sequences` lleva las **cinco** dimensiones del consecutivo. Con menos, la
  serie nace con huecos y Hacienda la rechaza; el porqué está en la migración.

Las dos heredan `TenantMixin`. `fe_credentials` sobre todo: dejarla fuera la
convertiría en la única tabla de negocio cuya lectura depende de que alguien se
acuerde de escribir el `WHERE`, y lo que se filtraría es de dónde sale la firma.
"""

from sqlalchemy import (
    CHAR,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    text,
)

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class FeCredentials(TenantMixin, Base):
    """Con qué firma y con qué transmite una compañía, en cada ambiente.

    **La llave privada no está acá.** Se importa a Vault al subir el `.p12` y no
    vuelve a salir, así que de la firma queda solo la parte pública. Tampoco
    está el PIN: solo sirve para abrir el `.p12`, eso pasa una sola vez, y lo
    que no se guarda no se filtra (plan §7.1, 2026-09-13).

    El único secreto que sí vive acá es la contraseña de ATV, porque hay que
    poder reenviarla al IdP en cada token. Va cifrada con AES-256-GCM y
    `(company_id, environment)` como dato asociado.
    """

    __tablename__ = "fe_credentials"

    # `PrimaryKeyConstraint` y no `primary_key=True` suelto: `company_id` lo
    # aporta el mixin y tiene que entrar en la llave compuesta junto con el
    # ambiente, que es lo que permite tener los dos juegos a la vez.
    __table_args__ = (PrimaryKeyConstraint("company_id", "environment"),)

    environment = Column(String(12), nullable=False)  # 'sandbox' | 'production'

    # --------------------------------------------------------------- firma
    #: La parte pública del certificado. NO es secreta: viaja en el `KeyInfo`
    #: de cada XML firmado, así que cifrarla sería teatro.
    certificate_pem = Column(Text, nullable=True)
    #: 'vault'; NULL es «esta compañía no tiene certificado en este ambiente».
    key_custody = Column(String(12), nullable=True)
    certificate_name = Column(String(160), nullable=True)
    #: DATETIME y no DATE: el `notAfter` tiene hora, y un certificado que vence
    #: a las 10:00 no sirve a las 11:00.
    expires_at = Column(DateTime, nullable=True)
    cert_uploaded_at = Column(DateTime, nullable=True)
    cert_uploaded_by = Column(Integer, nullable=True)

    # ---------------------------------------------------------- transmisión
    #: Identificador, no secreto: se muestra. Sin verlo, nadie puede comprobar
    #: que escribió el que era (RN-16).
    atv_user = Column(String(160), nullable=True)
    #: El AES-GCM en base64. Texto y no binario para que el modelo y la
    #: migración digan lo mismo sin un tipo propietario: `LargeBinary(512)`
    #: compila a `BLOB`, no a `VARBINARY`, y `test_esquema.py` lo caza.
    atv_password_encrypted = Column(String(512), nullable=True)
    #: Las marcas van en DOS PARES porque son dos secretos con vidas distintas:
    #: rotar la contraseña en marzo no puede hacer que la pantalla diga que el
    #: certificado se subió en marzo.
    atv_updated_at = Column(DateTime, nullable=True)
    atv_updated_by = Column(Integer, nullable=True)
    #: Última vez que el IdP entregó un token con estas credenciales. Es lo que
    #: permite decir «verificadas el 3 de septiembre» en vez de obligar a probar
    #: a ciegas.
    atv_verified_at = Column(DateTime, nullable=True)


class FeSequence(TenantMixin, Base):
    """Desde qué número sigue cada serie.

    La secuencia es **dentro del tipo de comprobante**: las facturas llevan la
    suya y los tiquetes la suya. Un contador por terminal produce series con
    saltos —1, 3, 5 y 2, 4— y «consecutivo fuera de orden» es rechazo.
    """

    __tablename__ = "fe_sequences"

    __table_args__ = (
        PrimaryKeyConstraint(
            "company_id", "branch_id", "terminal_id", "document_type", "environment"
        ),
    )

    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    terminal_id = Column(Integer, ForeignKey("terminals.id"), nullable=False)
    #: 01 factura, 02 nota de débito, 03 nota de crédito, 04 tiquete…
    document_type = Column(CHAR(2), nullable=False)
    environment = Column(String(12), nullable=False)

    #: BIGINT y no INT: son diez dígitos y 9 999 999 999 no cabe en un INT con
    #: signo. El techo solo se alcanza en un negocio enorme, pero el
    #: desbordamiento de MySQL no avisa.
    last_number = Column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(Integer, nullable=True)
