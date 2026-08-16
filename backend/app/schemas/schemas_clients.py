from pydantic import BaseModel
from datetime import date


class ClientRegister(BaseModel):
    # client attributes
    identification: str
    name: str
    last_name: str
    second_name: str
    email: str
    telephone: int | None = None
    address: str | None = None
    register_date: str | None = None

class ClientUpdate(BaseModel):
    identification: str | None = None
    name: str | None = None
    last_name: str | None = None
    second_name: str | None = None
    email: str | None = None
    telephone: int | None = None
    address: str | None = None
    register_date: str | None = None
    
class ClientResponse(BaseModel):
    id_client: int
    identification: str
    name: str
    last_name: str
    second_name: str
    email: str
    telephone: int | None = None
    address: str | None = None
    register_date: str | None = None

    model_config = {
        "from_attributes": True
    }

class ClientRegisterSuccess(BaseModel):
    message: str
    id_client: int

    model_config = {
        "from_attributes": True
    }
class ClientUserInformation(BaseModel):
    id_client: int
    identification: str
    name: str
    last_name: str
    second_name: str
    email: str
    telephone: int | None = None
    address: str | None = None
    register_date: date | None = None

    model_config = {
        "from_attributes": True
    }
class UpdateClientResponse(BaseModel):
    message: str
    id_client: int
