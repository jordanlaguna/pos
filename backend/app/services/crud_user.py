"""Usuarios de una compañía.

Un usuario es una identidad global —un correo, una contraseña—, pero desde el
POS solo se ven y se gestionan los de la compañía en la que se está trabajando.
De ahí que casi todo acá reciba `company_id`: la lista de «los usuarios» no
existe sin decir de quién.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.model_company import UserCompany
from app.models.model_user import User
from app.schemas.schemas_user import UserCreate
from app.utils.security import hash_password, verify_password
from app.utils.tenancy import sin_filtro

ROLES = ("admin", "cajero")


def get_users(db: Session, company_id: int) -> list[tuple[User, UserCompany]]:
    """Las personas con membresía en la compañía, con su rol ahí."""
    return (
        sin_filtro(
            db.query(User, UserCompany)
            .join(UserCompany, UserCompany.user_id == User.id_user)
            .filter(UserCompany.company_id == company_id)
            .order_by(User.id_user)
        )
    ).all()


def get_user(db: Session, user_id: int, company_id: int) -> tuple[User, UserCompany] | None:
    """Una persona, **si** pertenece a esta compañía.

    Devuelve `None` cuando no, y quien llama responde 404. Distinguir «no existe»
    de «existe pero no es tuyo» le confirmaría a una compañía los identificadores
    de otra.
    """
    return (
        sin_filtro(
            db.query(User, UserCompany)
            .join(UserCompany, UserCompany.user_id == User.id_user)
            .filter(User.id_user == user_id, UserCompany.company_id == company_id)
        )
    ).first()


def create_user(db: Session, user: UserCreate, company_id: int) -> tuple[User, UserCompany]:
    """Crea la identidad y su membresía en esta compañía, en una transacción."""
    rol = user.role if user.role in ROLES else "cajero"

    db_user = User(
        email=user.email,
        password=hash_password(user.password),
        id_person=user.id_person,
    )
    db.add(db_user)
    db.flush()  # necesitamos el id_user antes de crear la membresía

    ahora = datetime.now().replace(microsecond=0)
    membresia = UserCompany(
        user_id=db_user.id_user,
        company_id=company_id,
        rol=rol,
        activa=True,
        creada_el=ahora,
        # Nace aceptada, y no es una excepción a T-229: acá el administrador no
        # está agregando la cuenta de otro, la está **creando** —le puso el
        # correo y la contraseña—. Pedirle a esa cuenta que acepte una
        # invitación a sí misma no protegería a nadie.
        aceptada_el=ahora,
    )
    db.add(membresia)
    db.commit()
    db.refresh(db_user)
    return db_user, membresia


def grant_membership(db: Session, user_id: int, company_id: int, rol: str) -> UserCompany:
    """Invita a esta compañía a alguien que **ya tiene cuenta**.

    Queda **pendiente** (T-229): la membresía existe pero no autoriza nada hasta
    que la persona la acepte. Un administrador puede sumar a su compañía a quien
    quiera —es la única forma de armar el caso del contador que atiende varios
    locales— pero no puede darle acceso a su nombre ni llenarle la lista de
    compañías ajenas.

    Reactivar en vez de crear otra fila: el UNIQUE (user_id, company_id) lo
    impide, y además volver a invitar a quien rechazó no debería inventar una
    membresía nueva sin historia. Vuelve a quedar pendiente, no aceptada: haber
    dicho que no una vez no es haber dicho que sí.
    """
    existente = (
        sin_filtro(
            db.query(UserCompany).filter(
                UserCompany.user_id == user_id, UserCompany.company_id == company_id
            )
        )
    ).first()

    if existente:
        existente.rol = rol
        if not existente.activa:
            existente.activa = True
            existente.aceptada_el = None
        db.commit()
        db.refresh(existente)
        return existente

    membresia = UserCompany(
        user_id=user_id,
        company_id=company_id,
        rol=rol,
        activa=True,
        creada_el=datetime.now().replace(microsecond=0),
        aceptada_el=None,
    )
    db.add(membresia)
    db.commit()
    db.refresh(membresia)
    return membresia


def get_user_by_email(db: Session, email: str) -> User | None:
    # El correo es único en todo el sistema, no por compañía: es la identidad
    # con la que alguien se autentica antes de que se sepa dónde va a entrar.
    return sin_filtro(db.query(User).filter(User.email == email)).first()


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.password):
        return None
    return user
