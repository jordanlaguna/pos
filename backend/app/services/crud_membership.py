"""Membresías: a qué compañías puede entrar una persona, y con qué rol.

Todas las consultas de acá se hacen **antes** de que exista compañía en el
contexto —son las que dicen cuál puede haber—, así que van con el filtro
automático desactivado de forma explícita. `user_companies` y `companies` no
heredan `TenantMixin` justamente por eso; el filtro de cada consulta se escribe
a mano y está a la vista.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.model_company import AuditLog, Branch, Company, Terminal, UserCompany
from app.utils.tenancy import sin_filtro

#: Estados en los que se entra con normalidad. `vencida` entra a propósito: hay
#: siete días de gracia y, pasados esos, el sistema queda en solo lectura pero
#: la caja abierta siempre se puede cerrar (RN-1). Ese matiz lo aplica F3; acá
#: solo se decide si la puerta abre.
ESTADOS_QUE_ENTRAN = ("prueba", "activa", "vencida")

#: Con la suscripción suspendida solo entra el administrador, y solo para ver el
#: aviso de pago (spec §2). El cajero no puede hacer nada útil y verlo intentarlo
#: es peor que decirle por qué.
ESTADO_SOLO_ADMIN = "suspendida"


def companias_de(db: Session, user_id: int) -> list[tuple[UserCompany, Company]]:
    """Las membresías vigentes de una persona, con su compañía.

    Incluye las **invitaciones pendientes** (`aceptada_el` en nulo): la persona
    tiene que verlas para poder aceptarlas o rechazarlas. Quien las separa es
    quien llama; acá salen juntas porque son la misma fila.

    No incluye las desactivadas. Una membresía revocada —o una invitación
    rechazada— no es una compañía bloqueada: es alguien a quien no le
    corresponde ver que ese negocio existe. Por eso esa no se lista, mientras
    que una compañía suspendida sí.
    """
    return (
        sin_filtro(
            db.query(UserCompany, Company)
            .join(Company, Company.id == UserCompany.company_id)
            .filter(UserCompany.user_id == user_id, UserCompany.activa.is_(True))
            .order_by(Company.afiliado, Company.compania)
        )
    ).all()


def membresia(
    db: Session, user_id: int, company_id: int, *, incluir_pendientes: bool = False
) -> tuple[UserCompany, Company] | None:
    """La membresía **aceptada** de una persona en una compañía, o `None`.

    Por omisión no devuelve las invitaciones pendientes, y eso es a propósito:
    esta es la función que usa `get_current_user` en cada petición para decidir
    si la sesión sigue valiendo. Una invitación sin aceptar no autoriza nada.

    `incluir_pendientes` es para los dos únicos sitios que necesitan verla: la
    pantalla que la muestra y el endpoint que la acepta.
    """
    consulta = (
        db.query(UserCompany, Company)
        .join(Company, Company.id == UserCompany.company_id)
        .filter(
            UserCompany.user_id == user_id,
            UserCompany.company_id == company_id,
            UserCompany.activa.is_(True),
        )
    )
    if not incluir_pendientes:
        consulta = consulta.filter(UserCompany.aceptada_el.isnot(None))
    return sin_filtro(consulta).first()


def sucursal_y_terminal(db: Session, company_id: int) -> tuple[int | None, int | None]:
    """Dónde va a trabajar esta sesión.

    Por ahora, la primera sucursal activa de la compañía y su primera terminal
    activa. Alcanza mientras cada compañía tenga una de cada —que es el caso de
    todos los planes de hoy— y deja el lugar preparado para cuando el POS
    pregunte en qué caja se está abriendo, que es lo que hará falta el día que
    un negocio tenga tres.

    Va acá y no en el token del cliente porque es exactamente lo que no puede
    elegirse desde afuera (RN-14).
    """
    sucursal = (
        sin_filtro(
            db.query(Branch)
            .filter(Branch.company_id == company_id, Branch.activa.is_(True))
            .order_by(Branch.codigo, Branch.id)
        )
    ).first()
    if sucursal is None:
        return None, None

    terminal = (
        sin_filtro(
            db.query(Terminal)
            .filter(
                Terminal.company_id == company_id,
                Terminal.branch_id == sucursal.id,
                Terminal.activa.is_(True),
            )
            .order_by(Terminal.codigo, Terminal.id)
        )
    ).first()

    return sucursal.id, (terminal.id if terminal else None)


def compania(db: Session, company_id: int) -> Company | None:
    """La compañía por su id, sin pasar por el filtro (es la raíz, no se filtra)."""
    return sin_filtro(db.query(Company).filter(Company.id == company_id)).first()


def codigos(
    db: Session, branch_id: int | None, terminal_id: int | None
) -> tuple[str | None, str | None]:
    """Los códigos de sucursal y terminal, para mostrarlos en el menú.

    Se devuelven los códigos y no los identificadores porque son los que
    significan algo para quien los lee —y los mismos que van en el consecutivo
    del comprobante—: «001 · 00002» le dice al cajero en qué caja está.
    """
    sucursal = (
        sin_filtro(db.query(Branch).filter(Branch.id == branch_id)).first()
        if branch_id
        else None
    )
    terminal = (
        sin_filtro(db.query(Terminal).filter(Terminal.id == terminal_id)).first()
        if terminal_id
        else None
    )
    return (sucursal.codigo if sucursal else None), (terminal.codigo if terminal else None)


def puede_entrar(company: Company, rol: str) -> tuple[bool, str | None]:
    """¿Deja entrar el estado de la suscripción? Devuelve el motivo en código.

    El motivo es un código y no una frase: lo traduce el POS (RN-30).
    """
    if company.estado in ESTADOS_QUE_ENTRAN:
        return True, None
    if company.estado == ESTADO_SOLO_ADMIN:
        if rol == "admin":
            return True, None
        return False, "suspendida"
    # 'cancelada' y cualquier estado que se invente después: no entra nadie.
    # Es deliberadamente cerrado —un estado desconocido bloquea— porque la
    # alternativa es que un error de dedo en la base abra la puerta.
    return False, company.estado


def registrar(
    db: Session,
    *,
    user_id: int,
    company_id: int | None,
    accion: str,
    detalle: str | None = None,
    ip: str | None = None,
) -> None:
    """Anota en la bitácora. No hace commit: lo hace quien la llamó.

    Así la anotación entra en la misma transacción que el hecho que narra, y no
    puede quedar una sin el otro.
    """
    db.add(
        AuditLog(
            user_id=user_id,
            company_id=company_id,
            accion=accion,
            detalle=detalle,
            ip=ip,
            creado_el=datetime.now().replace(microsecond=0),
        )
    )
