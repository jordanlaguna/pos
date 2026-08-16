from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.model_person import Person
from app.models.model_user import User
from app.schemas.schemas_person import (
    PersonRegister,
    PersonRegisterSuccess,
    PersonUserInformation,
    UpdatePerson,
    UpdatePersonResponse,
)
from app.services import crud_person
from app.utils.auth_dependency import get_current_user, require_admin

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Sin autenticación a propósito: es la pantalla de registro, todavía no hay sesión.
@router.post("/register", response_model=PersonRegisterSuccess)
def register_person(person: PersonRegister, db: Session = Depends(get_db)):
    if db.query(Person).filter(Person.identification == person.identification).first():
        raise HTTPException(status_code=400, detail="Ya existe una persona con esta cédula.")
    if db.query(User).filter(User.email == person.email).first():
        raise HTTPException(status_code=400, detail="Ya existe un usuario con este correo.")

    return crud_person.create_person(db=db, person=person)


@router.get("/persons_list", response_model=List[PersonUserInformation])
def get_all_persons(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    rows = db.query(Person, User).join(User, Person.id_person == User.id_person).all()

    return [
        PersonUserInformation(
            id_person=person.id_person,
            birth_date=person.birth_date,
            identification=person.identification,
            name=person.name,
            lastName=person.lastName,
            secondName=person.secondName,
            telephone=person.telephone,
            id_user=user.id_user,
            email=user.email,
            role=user.role,
        )
        for person, user in rows
    ]


@router.put("/update/{id_person}", response_model=UpdatePersonResponse)
def update_person(
    id_person: int,
    person: UpdatePerson,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    # Cada quien edita sus propios datos; el admin puede editar los de cualquiera.
    if current.id_person != id_person and current.role != "admin":
        raise HTTPException(status_code=403, detail="No podés editar este usuario.")

    updated = crud_person.update_person_information(
        db=db, id_person=id_person, person_data=person.dict()
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Persona no encontrada.")

    return updated
