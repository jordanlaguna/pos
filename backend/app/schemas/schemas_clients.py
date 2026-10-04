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
    #: El tipo de Hacienda (T-617): '01' física, '02' jurídica, '03' DIMEX,
    #: '04' NITE, y desde T-727 '05' extranjero no domiciliado —que recibe
    #: factura de exportación— y '06' no contribuyente. Sin él se deduce de la
    #: cédula; si tampoco así se sabe, el cliente no se guarda.
    identification_type: str | None = None
    name: str
    last_name: str
    second_name: str
    email: str
    telephone: int | None = None
    address: str | None = None
    register_date: str | None = None
    #: Las otras señas de un cliente del extranjero (RF-78, T-727): van en el
    #: receptor de la factura de exportación en lugar de la ubicación del país.
    foreign_address: str | None = None

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
    #: Ausente o en blanco deja el que tenía.
    identification_type: str | None = None
    name: str | None = None
    last_name: str | None = None
    second_name: str | None = None
    email: str | None = None
    telephone: int | None = None
    address: str | None = None
    register_date: str | None = None
    #: Las otras señas de un cliente del extranjero (RF-78, T-727): van en el
    #: receptor de la factura de exportación en lugar de la ubicación del país.
    foreign_address: str | None = None

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
    identification_type: str | None = None
    name: str
    last_name: str
    second_name: str
    email: str
    telephone: int | None = None
    address: str | None = None
    register_date: str | None = None
    #: Las otras señas de un cliente del extranjero (RF-78, T-727): van en el
    #: receptor de la factura de exportación en lugar de la ubicación del país.
    foreign_address: str | None = None

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
    #: Lo imprime el comprobante en el receptor: «Cédula física 108840287».
    #: Nulo en un cliente que ni la migración 011 pudo clasificar.
    identification_type: str | None = None
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
