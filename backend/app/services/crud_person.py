from sqlalchemy.orm import Session

from app.models.model_person import Person
from app.models.model_user import User
from app.schemas.schemas_person import PersonRegister
from app.utils.security import hash_password


def create_person(db: Session, person: PersonRegister):
    db_person = Person(
        birth_date=person.birth_date,
        identification=person.identification,
        name=person.name,
        lastName=person.lastName,
        secondName=person.secondName,
        telephone=person.telephone,
    )
    db.add(db_person)
    db.flush()  # asigna id_person sin cerrar la transacción

    # El primer usuario del sistema es administrador —si no, nadie podría
    # gestionar nada—. A partir de ahí todos entran como cajero y el ascenso
    # lo concede un admin explícitamente.
    is_first_user = db.query(User).count() == 0

    db_user = User(
        email=person.email,
        password=hash_password(person.password),
        id_person=db_person.id_person,
        role="admin" if is_first_user else "cajero",
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    db.refresh(db_person)

    return {
        "message": "Registro exitoso",
        "id_user": db_user.id_user,
        "id_person": db_person.id_person,
    }


def get_allpersons_information(db: Session):
    return (
        db.query(Person, User)
        .join(User, Person.id_person == User.id_person)
        .all()
    )


def update_person_information(db: Session, id_person: int, person_data: dict):
    db_person = db.query(Person).filter(Person.id_person == id_person).first()
    db_user = db.query(User).filter(User.id_person == id_person).first()

    if not db_person or not db_user:
        return None

    for key, value in person_data.items():
        if value is None:
            continue
        if hasattr(db_person, key):
            setattr(db_person, key, value)
        elif key == "email":
            db_user.email = value
        # El rol se cambia solo desde PUT /users/role/{id}, nunca aquí: este
        # endpoint lo usa el propio usuario para editar sus datos.

    db.commit()
    db.refresh(db_person)

    return {"message": "Persona actualizada exitosamente", "id_person": id_person}
