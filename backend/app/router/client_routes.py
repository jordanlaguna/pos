from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.model_client import Client
from app.models.model_user import User
from app.schemas.schemas_clients import (
    ClientRegister,
    ClientRegisterSuccess,
    ClientUpdate,
    ClientUserInformation,
    UpdateClientResponse,
)
from app.services import crud_client
from app.utils.auth_dependency import get_current_user

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Los cajeros registran clientes en el mostrador, así que basta con estar autenticado.
@router.post("/register_client", response_model=ClientRegisterSuccess)
def register_client(
    client: ClientRegister,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    existing = db.query(Client).filter(Client.identification == client.identification).first()
    if existing:
        raise HTTPException(
            status_code=400, detail="Ya existe un cliente con esta identificación."
        )
    return crud_client.create_client(db=db, client=client)


@router.get("/clients_list", response_model=list[ClientUserInformation])
def get_clients_list(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return db.query(Client).order_by(Client.name).all()


@router.put("/update_client/{id_client}", response_model=UpdateClientResponse)
def update_client(
    id_client: int,
    client_data: ClientUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    existing = db.query(Client).filter(Client.id_client == id_client).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")

    # Una cédula repetida crearía dos fichas para la misma persona.
    if client_data.identification:
        clash = (
            db.query(Client)
            .filter(
                Client.identification == client_data.identification,
                Client.id_client != id_client,
            )
            .first()
        )
        if clash:
            raise HTTPException(
                status_code=400, detail="Ya existe otro cliente con esta identificación."
            )

    updated = crud_client.update_client_information(
        db=db, id_client=id_client, client_data=client_data.dict()
    )
    if not updated:
        raise HTTPException(
            status_code=400, detail="Error al actualizar la información del cliente."
        )
    return updated
