from datetime import date
from typing import Annotated

from pydantic import BaseModel, BeforeValidator


def _vacio_es_nulo(valor: object) -> object:
    """Un campo de formulario en blanco es «no hay valor», no un cero.

    El navegador manda `""` por un `<input>` vacío y Pydantic lo rechaza con un
    422 que no dice nada útil. Acá se traduce una vez, en la frontera, y los
    números de la exoneración —artículo, inciso y puntos— aceptan las dos
    formas sin que el POS tenga que acordarse de mandar `null`.
    """
    return None if valor == "" else valor


#: Un entero de formulario: acepta el blanco como nulo.
EnteroDeFormulario = Annotated[int | None, BeforeValidator(_vacio_es_nulo)]
#: Lo mismo para un decimal.
DecimalDeFormulario = Annotated[float | None, BeforeValidator(_vacio_es_nulo)]


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

    # --- F7: la exoneración del cliente (RF-67, RN-78) ----------------------
    #
    # **Son puntos de tarifa, no una tarifa**: 9 es nueve puntos, así que una
    # línea al 13 % pasa a pagar 4 %. Los ocho se ponen y se quitan juntos; si
    # viene cualquiera, vienen todos.
    exo_document_type: str | None = None
    exo_document_number: str | None = None
    exo_institution: str | None = None
    exo_institution_other: str | None = None
    exo_article: EnteroDeFormulario = None
    exo_subsection: EnteroDeFormulario = None
    exo_date: str | None = None
    exo_points: DecimalDeFormulario = None

class ClientUpdate(BaseModel):
    identification: str | None = None
    name: str | None = None
    last_name: str | None = None
    second_name: str | None = None
    email: str | None = None
    telephone: int | None = None
    address: str | None = None
    register_date: str | None = None

    # --- F7: la exoneración del cliente (RF-67, RN-78) ----------------------
    #
    # **Son puntos de tarifa, no una tarifa**: 9 es nueve puntos, así que una
    # línea al 13 % pasa a pagar 4 %. Los ocho se ponen y se quitan juntos; si
    # viene cualquiera, vienen todos.
    exo_document_type: str | None = None
    exo_document_number: str | None = None
    exo_institution: str | None = None
    exo_institution_other: str | None = None
    exo_article: EnteroDeFormulario = None
    exo_subsection: EnteroDeFormulario = None
    exo_date: str | None = None
    exo_points: DecimalDeFormulario = None

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

    # --- F7: la exoneración del cliente (RF-67, RN-78) ----------------------
    #
    # **Son puntos de tarifa, no una tarifa**: 9 es nueve puntos, así que una
    # línea al 13 % pasa a pagar 4 %. Los ocho se ponen y se quitan juntos; si
    # viene cualquiera, vienen todos.
    exo_document_type: str | None = None
    exo_document_number: str | None = None
    exo_institution: str | None = None
    exo_institution_other: str | None = None
    exo_article: EnteroDeFormulario = None
    exo_subsection: EnteroDeFormulario = None
    exo_date: date | None = None
    exo_points: DecimalDeFormulario = None

    model_config = {
        "from_attributes": True
    }
class UpdateClientResponse(BaseModel):
    message: str
    id_client: int
