from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.domain.errors import IdentificationTypeRequired, InvalidIdentificationType
from app.domain.fe_exemptions import Exemption, InvalidExemption
from app.domain.hacienda import check_identification_type, client_identification_type
from app.models.model_client import Client
from app.schemas.schemas_clients import ClientRegister
from app.utils.api_errors import api_error

#: Los ocho campos de la exoneración, en el orden en que los pide el XML.
#:
#: **Se tratan como uno solo.** Una exoneración a medias no es válida en ningún
#: contexto: si viene cualquiera de los ocho, vienen los ocho, y lo que falte es
#: un «no» y no un valor por omisión (RN-78).
CAMPOS_EXONERACION = (
    "exo_document_type",
    "exo_document_number",
    "exo_institution",
    "exo_institution_other",
    "exo_article",
    "exo_subsection",
    "exo_date",
    "exo_points",
)

SIN_EXONERACION = dict.fromkeys(CAMPOS_EXONERACION, None)


def _fecha(valor: object) -> date | None:
    """La fecha del documento, venga como día o como fecha y hora completa.

    El XML pide un `dateTime` y el formulario manda un día; los ejemplos reales
    traen todos `T00:00:00`, así que la hora no es un dato que nadie tenga. Se
    guarda el día y la hora se pone al emitir.
    """
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return datetime.fromisoformat(str(valor)).date()
    except ValueError:
        raise api_error(400, "invalid_exemption", reason="bad_date") from None


def _puntos(valor: object) -> Decimal:
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise api_error(400, "invalid_exemption", reason="points_out_of_range") from None


def revisar_exoneracion(datos: dict) -> dict:
    """Los ocho campos comprobados, o los ocho en nulo, o 400.

    Devuelve siempre el grupo entero, y eso es el punto: **la exoneración se
    pone y se quita de una pieza**. Guardar la mitad dejaría un cliente con un
    número de documento y sin institución, y eso no se descubre hasta que
    Hacienda rechaza la factura.
    """
    if not any(k in datos for k in CAMPOS_EXONERACION):
        return {}

    crudos = {k: datos.get(k) for k in CAMPOS_EXONERACION}
    if not any(v not in (None, "") for v in crudos.values()):
        # Los ocho vacíos es «este cliente no tiene exoneración», que es lo
        # normal y es también cómo se le quita la que tenía.
        return dict(SIN_EXONERACION)

    fecha = _fecha(crudos["exo_date"])
    try:
        exo = Exemption(
            document_type=str(crudos["exo_document_type"] or ""),
            document_number=str(crudos["exo_document_number"] or ""),
            institution=str(crudos["exo_institution"] or ""),
            institution_other=str(crudos["exo_institution_other"] or ""),
            # Ya son enteros o nulos: el esquema los convierte en la frontera
            # y un «diecisiete» no llega hasta acá, se va en un 422.
            article=crudos["exo_article"],
            subsection=crudos["exo_subsection"],
            date=fecha.isoformat() if fecha else "",
            points=_puntos(crudos["exo_points"]),
        )
    except InvalidExemption as error:
        raise api_error(400, "invalid_exemption", reason=error.code) from None

    return {
        "exo_document_type": exo.document_type,
        "exo_document_number": exo.document_number,
        "exo_institution": exo.institution,
        "exo_institution_other": exo.institution_other or None,
        "exo_article": exo.article,
        "exo_subsection": exo.subsection,
        "exo_date": fecha,
        "exo_points": exo.points,
    }


def _tipo(requested: object, identification: str) -> str:
    """El tipo de identificación con que se guarda (T-617), o el «no» con su código."""
    try:
        return client_identification_type(requested, identification)
    except InvalidIdentificationType:
        raise api_error(
            400, "invalid_identification_type", identification_type=str(requested)
        ) from None
    except IdentificationTypeRequired:
        raise api_error(400, "identification_type_required") from None


def create_client(db: Session, client: ClientRegister):
    db_client = Client(
        identification=client.identification,
        identification_type=_tipo(client.identification_type, client.identification),
        name=client.name,
        last_name=client.last_name,
        second_name=client.second_name,
        email=client.email,
        telephone=client.telephone,
        address=client.address,
        register_date=client.register_date,
        **revisar_exoneracion(client.model_dump(exclude_unset=True)),
    )
    db.add(db_client)
    db.commit()
    db.refresh(db_client)

    return {
        "message": "client_registered",
        "id_client": db_client.id_client
    }

def get_all_clients_information(db: Session):
    # Retrieve all clients from the database
    return db.query(Client).all()

# Update client information
def update_client_information(db: Session, id_client: int, client_data: dict):
    db_client = db.query(Client).filter(Client.id_client == id_client).first()

    if not db_client:
        return None

    # La exoneración se comprueba y se asigna entera, antes del bucle: sus ocho
    # campos se ponen y se quitan juntos, y el nulo en ellos **es** un valor.
    exoneracion = revisar_exoneracion(client_data)
    for key, value in exoneracion.items():
        setattr(db_client, key, value)

    # El tipo se cambia solo si viene con valor (T-617): en blanco es «no lo
    # toqué», como el resto de los campos de esta ficha.
    tipo = client_data.pop("identification_type", None)
    if tipo not in (None, ""):
        try:
            db_client.identification_type = check_identification_type(tipo)
        except InvalidIdentificationType:
            raise api_error(
                400, "invalid_identification_type", identification_type=str(tipo)
            ) from None

    for key, value in client_data.items():
        if key in CAMPOS_EXONERACION:
            continue
        if value is not None:
            # Update fields in Client
            if hasattr(db_client, key):
                setattr(db_client, key, value)
            else:
                raise ValueError(f"Unknown field: {key}")

    db.commit()
    db.refresh(db_client)

    return {
        "message": "client_updated",
        "id_client": db_client.id_client
    }
