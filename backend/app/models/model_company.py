"""Compañías, planes, sucursales, terminales, membresías y bitácora (T-201).

Es la raíz del modelo multiempresa: todo lo demás cuelga de `companies`.

Cuáles heredan `TenantMixin` y cuáles no:

* `Branch` y `Terminal` sí. Son datos de una compañía y listarlos tiene que
  devolver los suyos, igual que los productos.
* `Company` y `Plan` no. `companies` es la raíz —no pertenece a una compañía,
  *es* la compañía— y `plans` es el catálogo de suscripciones, común a todas.
* `UserCompany` no, aunque tenga `company_id`. Se lee en el login, antes de que
  exista compañía en el contexto: es justo la tabla que dice cuál puede haber.
  Sus consultas llevan el filtro escrito a mano, que es lo correcto acá.
* `AuditLog` tampoco: su `company_id` es nulo cuando la acción no es sobre
  ninguna compañía —soporte entrando, un intento de login fallido—.
"""

from sqlalchemy import (
    CHAR,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class Plan(Base):
    """Los límites que se venden. Un plan no es una lista de precios sino lo que
    el sistema deja hacer: cuántas sucursales, cuántas cajas, cuánta gente.

    Y **qué módulos incluye** (T-1001, RN-49 a RN-51). Compras, contabilidad y
    planilla se venden aparte, y el sitio donde se dice qué se vende es este:
    un interruptor por compañía además del plan serían dos verdades sobre lo
    mismo. `factura_electronica` ya era una de estas banderas desde la 002.
    """

    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(60), nullable=False)
    precio_mensual = Column(
        Numeric(10, 2), nullable=False, default=0, server_default=text("0")
    )
    max_sucursales = Column(Integer, nullable=False, default=1, server_default=text("1"))
    max_terminales = Column(Integer, nullable=False, default=1, server_default=text("1"))
    max_usuarios = Column(Integer, nullable=False, default=3, server_default=text("3"))
    # Booleano y no entero: MySQL lo guarda igual —TINYINT(1)— pero así el
    # modelo dice lo mismo que la migración, y una instalación nueva no
    # queda con un esquema distinto de una migrada.
    factura_electronica = Column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )

    # Los tres módulos de F10 a F12 (migración 008). En **inglés**, al lado de
    # las columnas en español que vienen de la 002: esa excepción es de las que
    # ya existen y no una licencia para las nuevas (plan §3.9, T-913).
    #
    # Apagados por omisión, y no es un detalle: un plan que ya existe es uno que
    # alguien compró sin estos módulos. Encenderlos es trabajo de soporte.
    purchases = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    accounting = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    payroll = Column(Boolean, nullable=False, default=False, server_default=text("0"))


class Company(Base):
    """Un cliente del producto.

    Su identidad para el negocio es el par (afiliado, compañía) —así se
    identifican los clientes en el sistema del que viene VentaSys—, y el `id` es
    solo la llave técnica: existe para que las claves foráneas de las doce
    tablas de negocio ocupen 4 bytes y no 8.
    """

    __tablename__ = "companies"

    # El par es la identidad del cliente, así que el UNIQUE es la regla y no una
    # optimización: sin él, dos altas simultáneas eligen el mismo número (el
    # backend lo calcula con `siguiente_par`) y quedan dos clientes con la misma
    # identidad. El índice por estado es el que usa el listado del panel.
    __table_args__ = (
        UniqueConstraint("afiliado", "compania", name="uq_companies_afiliado_compania"),
        Index("idx_companies_estado", "estado"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    afiliado = Column(Integer, nullable=False)
    compania = Column(Integer, nullable=False)
    nombre = Column(String(160), nullable=False)
    identificacion = Column(String(30), nullable=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    # 'prueba' | 'activa' | 'vencida' | 'suspendida' | 'cancelada' (spec §2)
    estado = Column(
        String(20), nullable=False, default="prueba", server_default="prueba"
    )
    vence_el = Column(Date, nullable=True)
    creada_el = Column(DateTime, nullable=False)

    # Idioma de la pantalla y idioma de los documentos, separados a propósito:
    # la factura es para el cliente y para Hacienda, no para el cajero (RN-29).
    locale = Column(String(10), nullable=False, default="es", server_default="es")
    document_locale = Column(
        String(10), nullable=False, default="es", server_default="es"
    )


class Branch(TenantMixin, Base):
    """Sucursal. El código de 3 dígitos es el que Hacienda pide en el
    consecutivo del comprobante, así que se guarda con ese formato desde ya."""

    __tablename__ = "branches"

    # El código no se repite dentro de una compañía: es el que va en el
    # consecutivo del comprobante, y dos sucursales con el mismo código
    # producirían dos facturas con la misma numeración ante Hacienda.
    __table_args__ = (
        UniqueConstraint("company_id", "codigo", name="uq_branches"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(CHAR(3), nullable=False)
    nombre = Column(String(120), nullable=False)
    activa = Column(Boolean, nullable=False, default=True, server_default=text("1"))


class Terminal(TenantMixin, Base):
    """Caja. Cinco dígitos, misma razón que la sucursal."""

    __tablename__ = "terminals"

    # Lleva la sucursal adentro: el código de terminal es único **por sucursal**,
    # no por compañía. Dos locales pueden tener los dos su caja «00001».
    __table_args__ = (
        UniqueConstraint("company_id", "branch_id", "codigo", name="uq_terminals"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    codigo = Column(CHAR(5), nullable=False)
    nombre = Column(String(120), nullable=False)
    activa = Column(Boolean, nullable=False, default=True, server_default=text("1"))


class UserCompany(Base):
    """Membresía: qué persona entra a qué compañía y con qué rol.

    El rol vive acá y no en `users` porque es por compañía: la misma persona
    puede ser administradora en su negocio y cajera en el de un socio (RN-3).
    """

    __tablename__ = "user_companies"

    # El UNIQUE es lo único que impide una membresía duplicada —la misma persona
    # dos veces en la misma compañía, con dos roles que se contradicen—.
    #
    # El índice aparte hace falta porque en el UNIQUE `company_id` va segunda, y
    # un índice solo sirve por su prefijo izquierdo: «quiénes pertenecen a esta
    # compañía» —la consulta del panel y la del login— no lo puede usar.
    __table_args__ = (
        UniqueConstraint("user_id", "company_id", name="uq_user_companies"),
        Index("idx_user_companies_company", "company_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    # 'admin' | 'cajero'
    rol = Column(String(20), nullable=False)
    activa = Column(Boolean, nullable=False, default=True, server_default=text("1"))
    creada_el = Column(DateTime, nullable=False)

    # Cuándo la aceptó la persona. NULL es «invitada, sin aceptar» (T-229), y es
    # distinto de una fecha vieja: la ausencia de fecha es la ausencia de
    # consentimiento. Un administrador puede agregar a su compañía a alguien que
    # ya tiene cuenta, pero no puede darle acceso a su nombre.
    aceptada_el = Column(DateTime, nullable=True)


class AuditLog(Base):
    """Quién hizo qué y sobre qué compañía.

    Sin clave foránea a `companies` a propósito: la bitácora tiene que
    sobrevivir al borrado de aquello que narra. Si al dar de baja a un cliente
    desaparece el rastro de lo que se hizo con su cuenta, no era una bitácora.
    """

    __tablename__ = "audit_log"

    # Los dos índices que declara la migración, declarados también acá: una
    # instalación nueva arma el esquema con `create_all` y una vieja lo trae de
    # la migración, así que lo que no esté en los dos lados hace que el mismo
    # código corra sobre esquemas distintos. El primero responde «qué se hizo en
    # esta compañía» y el segundo «qué se hizo, en cualquiera, últimamente»
    # —que es con lo que abre el panel de soporte (T-307)—.
    __table_args__ = (
        Index("idx_audit_company", "company_id", "creado_el"),
        Index("idx_audit_creado", "creado_el"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    company_id = Column(Integer, nullable=True)
    accion = Column(String(60), nullable=False)
    detalle = Column(String(500), nullable=True)
    ip = Column(String(45), nullable=True)
    creado_el = Column(DateTime, nullable=False)
