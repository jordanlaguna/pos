"""Lo que ve y hace el panel de soporte (T-303, T-305, T-307).

Todas las consultas de acá **cruzan compañías a propósito**, que es lo que hace
soporte: mirar el sistema entero. Van con `sin_filtro` y con el `company_id`
escrito a mano cuando hace falta, porque la sesión de soporte no tiene compañía
—no puede tenerla (RN-4)— y el filtro automático de `tenancy.py` haría fallar
cerrado cada una.

Que la marca `sin_filtro` aparezca en este archivo veinte veces es la intención
del diseño: `git grep sin_filtro` tiene que devolver el login, el panel de
soporte y los guiones de mantenimiento, y nada más.

**El uso se cuenta agrupando, no compañía por compañía.** Con veinte clientes,
cuatro métricas y una consulta por cada una serían ochenta viajes a la base para
pintar una tabla. Son cuatro consultas agrupadas por `company_id` y un `dict`.
Y se cuenta con `func.count(...)` y no con el `count` de `Query`: ese envuelve la
consulta en una subconsulta donde el criterio de compañía no entra —la trampa
que documenta `tests/test_tenancy.py`, que por eso no tolera esas cuatro letras
ni dentro de un comentario—.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain.limits import cupo
from app.domain.modules import MODULES, Modules
from app.domain.subscription import Suscripcion, evaluar
from app.models.model_company import AuditLog, Company, Plan, Terminal, UserCompany
from app.models.model_person import Person
from app.models.model_product import Product
from app.models.model_sales import Sale
from app.models.model_user import User
from app.utils import clock
from app.utils.tenancy import sin_filtro

#: Cuántas líneas de bitácora devuelve el panel de una vez. Sin tope, la
#: consulta crece con la vida del sistema entero: cada login de cada compañía
#: deja una línea.
BITACORA_POR_PAGINA = 50
BITACORA_MAXIMO = 500


# --------------------------------------------------------------------------
# El uso de cada compañía (RF-5)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Uso:
    """Cuánto de su plan está usando una compañía."""

    usuarios: int
    terminales: int
    productos: int
    ventas_del_mes: int
    total_del_mes: float

    #: Cuántos más caben, o `None` si el plan no limita. Se calcula acá y no en
    #: la pantalla para que la aritmética del plan viva en un solo lado.
    cupo_usuarios: int | None = None
    cupo_terminales: int | None = None


def _primer_dia_del_mes(hoy: date) -> datetime:
    return datetime(hoy.year, hoy.month, 1)


def _por_compania(filas) -> dict[int, int]:
    return {cid: total for cid, total in filas}


def uso_de_todas(db: Session, hoy: date | None = None) -> dict[int, Uso]:
    """El uso de todas las compañías, en cuatro consultas.

    `hoy` entra como argumento para que la prueba pueda pararse en un mes
    concreto. Por omisión, el reloj del servidor —nunca el del cliente—.
    """
    desde = _primer_dia_del_mes(hoy or clock.today())

    usuarios = _por_compania(
        sin_filtro(
            db.query(UserCompany.company_id, func.count(UserCompany.id))
            .filter(UserCompany.activa.is_(True))
            .group_by(UserCompany.company_id)
        ).all()
    )
    terminales = _por_compania(
        sin_filtro(
            db.query(Terminal.company_id, func.count(Terminal.id))
            .filter(Terminal.activa.is_(True))
            .group_by(Terminal.company_id)
        ).all()
    )
    productos = _por_compania(
        sin_filtro(
            db.query(Product.company_id, func.count(Product.id_product)).group_by(
                Product.company_id
            )
        ).all()
    )
    ventas = {
        cid: (cantidad, float(total or 0))
        for cid, cantidad, total in sin_filtro(
            db.query(Sale.company_id, func.count(Sale.id), func.sum(Sale.total))
            .filter(Sale.created_at >= desde)
            .group_by(Sale.company_id)
        ).all()
    }

    companias = sin_filtro(db.query(Company.id, Company.plan_id)).all()
    limites = {p.id: p for p in sin_filtro(db.query(Plan)).all()}

    resultado: dict[int, Uso] = {}
    for cid, plan_id in companias:
        plan = limites.get(plan_id)
        cantidad, total = ventas.get(cid, (0, 0.0))
        resultado[cid] = Uso(
            usuarios=usuarios.get(cid, 0),
            terminales=terminales.get(cid, 0),
            productos=productos.get(cid, 0),
            ventas_del_mes=cantidad,
            total_del_mes=total,
            cupo_usuarios=cupo(usuarios.get(cid, 0), plan.max_usuarios) if plan else None,
            cupo_terminales=cupo(terminales.get(cid, 0), plan.max_terminales) if plan else None,
        )
    return resultado


# --------------------------------------------------------------------------
# El listado (T-303)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CompaniaConEstado:
    """Una compañía como la ve soporte: sus datos, su plan, su estado y su uso."""

    company: Company
    plan: Plan | None
    suscripcion: Suscripcion
    uso: Uso
    #: Correos de los administradores, para saber a quién escribirle.
    administradores: list[str]


def _administradores(db: Session) -> dict[int, list[str]]:
    filas = sin_filtro(
        db.query(UserCompany.company_id, User.email)
        .join(User, User.id_user == UserCompany.user_id)
        .filter(UserCompany.rol == "admin", UserCompany.activa.is_(True))
        .order_by(UserCompany.company_id, User.email)
    ).all()
    correos: dict[int, list[str]] = {}
    for cid, email in filas:
        correos.setdefault(cid, []).append(email)
    return correos


def companias(db: Session, hoy: date | None = None) -> list[CompaniaConEstado]:
    """Todas las compañías del sistema, con lo que hace falta para gestionarlas.

    Sin paginar a propósito: son los clientes del producto y la lista es la
    herramienta de trabajo. El día que sean cientos habrá que paginar, y ese día
    se sabrá porque la pantalla tarda —no antes—.
    """
    dia = hoy or clock.today()
    usos = uso_de_todas(db, dia)
    correos = _administradores(db)
    planes = {p.id: p for p in sin_filtro(db.query(Plan)).all()}
    vacio = Uso(usuarios=0, terminales=0, productos=0, ventas_del_mes=0, total_del_mes=0.0)

    filas = sin_filtro(
        db.query(Company).order_by(Company.afiliado, Company.compania)
    ).all()

    return [
        CompaniaConEstado(
            company=c,
            plan=planes.get(c.plan_id),
            suscripcion=evaluar(c.estado, c.vence_el, dia),
            uso=usos.get(c.id, vacio),
            administradores=correos.get(c.id, []),
        )
        for c in filas
    ]


def una_compania(db: Session, company_id: int, hoy: date | None = None) -> CompaniaConEstado | None:
    """La ficha de una compañía. Se apoya en el listado para no tener dos formas
    distintas de calcular lo mismo; con la cantidad de compañías que puede tener
    una instalación, la diferencia no se mide."""
    for fila in companias(db, hoy):
        if fila.company.id == company_id:
            return fila
    return None


# --------------------------------------------------------------------------
# Cambiar la suscripción (T-305, RF-7)
# --------------------------------------------------------------------------


def cambiar_suscripcion(
    company: Company,
    *,
    estado: str,
    vence_el: date | None,
    plan: Plan | None = None,
) -> str:
    """Aplica el cambio y devuelve el detalle para la bitácora.

    El detalle se arma acá, con el antes y el después, porque es lo único que
    hace útil una bitácora: «cambió el estado» no sirve para nada dentro de seis
    meses y «activa → suspendida, vence 2026-09-30» sí.
    """
    partes = []
    if company.estado != estado:
        partes.append(f"estado {company.estado} → {estado}")
    if company.vence_el != vence_el:
        partes.append(f"vence {company.vence_el or 'sin fecha'} → {vence_el or 'sin fecha'}")
    if plan is not None and company.plan_id != plan.id:
        partes.append(f"plan {company.plan_id} → {plan.id} ({plan.nombre})")

    company.estado = estado
    company.vence_el = vence_el
    if plan is not None:
        company.plan_id = plan.id

    return ", ".join(partes) if partes else "sin cambios"


# --------------------------------------------------------------------------
# Los módulos de un plan (T-1003, RF-39)
# --------------------------------------------------------------------------


def cambiar_modulos(db: Session, plan: Plan, modulos: Modules) -> str:
    """Aplica los módulos del plan y devuelve el detalle para la bitácora.

    El detalle trae el antes, el después y **a cuántas compañías alcanza**, que
    es lo que lo distingue de cambiarle el plan a un cliente: acá se toca el
    catálogo y el efecto es de todos los que están en él.

    Sin cambios no miente: dice «sin cambios» en vez de inventar una línea, igual
    que `cambiar_suscripcion`.
    """
    partes = [
        f"{nombre} {'sí' if getattr(plan, nombre) else 'no'} → "
        f"{'sí' if modulos.includes(nombre) else 'no'}"
        for nombre in MODULES
        if bool(getattr(plan, nombre)) != modulos.includes(nombre)
    ]
    for nombre in MODULES:
        setattr(plan, nombre, modulos.includes(nombre))

    if not partes:
        return f"{plan.nombre}: sin cambios"

    alcanzadas = (
        sin_filtro(db.query(func.count(Company.id)).filter(Company.plan_id == plan.id))
    ).scalar() or 0
    return f"{plan.nombre}: {', '.join(partes)} ({alcanzadas} compañías)"


# --------------------------------------------------------------------------
# La bitácora (T-307, RF-9)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LineaDeBitacora:
    """Una línea de la bitácora con los nombres ya resueltos.

    Quién, qué, cuándo y sobre qué compañía. El correo y el nombre de la
    compañía se traen en la misma consulta: sin eso, la pantalla mostraría
    números de usuario, que es tener la bitácora y no poder leerla.
    """

    id: int
    creado_el: datetime
    user_id: int
    email: str | None
    nombre: str | None
    company_id: int | None
    company_nombre: str | None
    accion: str
    detalle: str | None
    ip: str | None


def bitacora(
    db: Session,
    *,
    company_id: int | None = None,
    accion: str | None = None,
    limite: int = BITACORA_POR_PAGINA,
) -> list[LineaDeBitacora]:
    """Las últimas líneas, de una compañía o de todas.

    Ordenadas por fecha descendente: lo que se busca en una bitácora es «qué
    pasó hace un rato». El `limite` se topa en `BITACORA_MAXIMO` para que un
    parámetro suelto no se convierta en una consulta de toda la tabla.
    """
    consulta = (
        db.query(AuditLog, User.email, Person.name, Person.lastName, Company.nombre)
        # `outerjoin` en los tres: la bitácora sobrevive a lo que narra. Si se da
        # de baja a un cliente, sus líneas siguen ahí con la compañía en nulo, y
        # un `join` normal las haría desaparecer justo cuando más importan.
        .outerjoin(User, User.id_user == AuditLog.user_id)
        .outerjoin(Person, Person.id_person == User.id_person)
        .outerjoin(Company, Company.id == AuditLog.company_id)
        .order_by(AuditLog.creado_el.desc(), AuditLog.id.desc())
    )
    if company_id is not None:
        consulta = consulta.filter(AuditLog.company_id == company_id)
    if accion:
        consulta = consulta.filter(AuditLog.accion == accion)

    filas = sin_filtro(consulta.limit(max(1, min(limite, BITACORA_MAXIMO)))).all()

    return [
        LineaDeBitacora(
            id=linea.id,
            creado_el=linea.creado_el,
            user_id=linea.user_id,
            email=email,
            nombre=f"{nombre or ''} {apellido or ''}".strip() or None,
            company_id=linea.company_id,
            company_nombre=company_nombre,
            accion=linea.accion,
            detalle=linea.detalle,
            ip=linea.ip,
        )
        for linea, email, nombre, apellido, company_nombre in filas
    ]


def acciones(db: Session) -> list[str]:
    """Las acciones que existen en la bitácora, para poder filtrar por ellas.

    Se leen de los datos y no de una lista escrita a mano: una acción nueva
    aparece en el filtro el día que ocurre por primera vez, sin que nadie tenga
    que acordarse de agregarla.
    """
    return [
        accion
        for (accion,) in sin_filtro(
            db.query(AuditLog.accion).distinct().order_by(AuditLog.accion)
        ).all()
    ]
