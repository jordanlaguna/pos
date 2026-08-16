from sqlalchemy.orm import Session

from app.models.model_user import User
from app.schemas.schemas_user import UserCreate
from app.utils.security import hash_password, verify_password


def get_users(db: Session):
    return db.query(User).order_by(User.id_user).all()


def get_user(db: Session, user_id: int):
    return db.query(User).filter(User.id_user == user_id).first()


def create_user(db: Session, user: UserCreate):
    db_user = User(
        email=user.email,
        password=hash_password(user.password),
        id_person=user.id_person,
        role=user.role if user.role in ("admin", "cajero") else "cajero",
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()


def authenticate_user(db: Session, email: str, password: str):
    user = get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.password):
        return None
    return user
