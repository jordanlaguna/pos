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

from sqlalchemy import CHAR, Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String

from app.database.database import Base
from app.utils.tenancy import TenantMixin


class Plan(Base):
    """Los límites que se venden. Un plan no es una lista de precios sino lo que
    el sistema deja hacer: cuántas sucursales, cuántas cajas, cuánta gente."""

    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(60), nullable=False)
    precio_mensual = Column(Numeric(10, 2), nullable=False, default=0)
    max_sucursales = Column(Integer, nullable=False, default=1)
    max_terminales = Column(Integer, nullable=False, default=1)
    max_usuarios = Column(Integer, nullable=False, default=3)
    # Booleano y no entero: MySQL lo guarda igual —TINYINT(1)— pero así el
    # modelo dice lo mismo que la migración, y una instalación nueva no
    # queda con un esquema distinto de una migrada.
    factura_electronica = Column(Boolean, nullable=False, default=False)


class Company(Base):
    """Un cliente del producto.

    Su identidad para el negocio es el par (afiliado, compañía) —así se
    identifican los clientes en el sistema del que viene VentaSys—, y el `id` es
    solo la llave técnica: existe para que las claves foráneas de las doce
    tablas de negocio ocupen 4 bytes y no 8.
    """

    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    afiliado = Column(Integer, nullable=False)
    compania = Column(Integer, nullable=False)
    nombre = Column(String(160), nullable=False)
    identificacion = Column(String(30), nullable=True)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    # 'prueba' | 'activa' | 'vencida' | 'suspendida' | 'cancelada' (spec §2)
    estado = Column(String(20), nullable=False, default="prueba")
    vence_el = Column(Date, nullable=True)
    creada_el = Column(DateTime, nullable=False)

    # Idioma de la pantalla y idioma de los documentos, separados a propósito:
    # la factura es para el cliente y para Hacienda, no para el cajero (RN-29).
    locale = Column(String(10), nullable=False, default="es")
    document_locale = Column(String(10), nullable=False, default="es")


class Branch(TenantMixin, Base):
    """Sucursal. El código de 3 dígitos es el que Hacienda pide en el
    consecutivo del comprobante, así que se guarda con ese formato desde ya."""

    __tablename__ = "branches"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    codigo = Column(CHAR(3), nullable=False)
    nombre = Column(String(120), nullable=False)
    activa = Column(Boolean, nullable=False, default=True)


class Terminal(TenantMixin, Base):
    """Caja. Cinco dígitos, misma razón que la sucursal."""

    __tablename__ = "terminals"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    codigo = Column(CHAR(5), nullable=False)
    nombre = Column(String(120), nullable=False)
    activa = Column(Boolean, nullable=False, default=True)


class UserCompany(Base):
    """Membresía: qué persona entra a qué compañía y con qué rol.

    El rol vive acá y no en `users` porque es por compañía: la misma persona
    puede ser administradora en su negocio y cajera en el de un socio (RN-3).
    """

    __tablename__ = "user_companies"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    # 'admin' | 'cajero'
    rol = Column(String(20), nullable=False)
    activa = Column(Boolean, nullable=False, default=True)
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

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    company_id = Column(Integer, nullable=True)
    accion = Column(String(60), nullable=False)
    detalle = Column(String(500), nullable=True)
    ip = Column(String(45), nullable=True)
    creado_el = Column(DateTime, nullable=False)
