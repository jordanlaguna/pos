"""
Factura electrónica: certificado y credenciales (F6, RF-22 a RF-24, RF-29, RF-30).

**Todo es de administrador**, y no solo por prudencia: con eso el bloqueo por
suscripción las alcanza sin tocar nada (plan §4.4), porque vive en
`get_current_user` y se aplica a lo que escribe.

**No hay ninguna ruta que devuelva el archivo, el PIN ni la contraseña**, y esa
ausencia es el contrato (RF-23, RN-16): no existe el camino. Desde que la llave
privada vive en Vault, el PIN además no se guarda en ninguna parte.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.schemas.schemas_einvoice import DocumentFileOut, QueueOut
from app.schemas.schemas_fe import (
    ActiveEnvironmentIn,
    AtvIn,
    FeStatusOut,
    SequencesOut,
    SequenceStartIn,
    SequenceStartOut,
)
from app.services import crud_fe, crud_fe_documents, crud_fe_sequences
from app.utils.auth_dependency import Sesion, get_current_user, get_db, require_admin

router = APIRouter()


@router.get("", response_model=FeStatusOut)
def estado(
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Qué tiene y qué le falta a **cada** ambiente (RF-23, RF-30)."""
    return crud_fe.estado(db)


@router.post("/{ambiente}/certificate", response_model=FeStatusOut)
async def subir_certificado(
    ambiente: str,
    archivo: UploadFile = File(...),
    pin: str = Form(...),
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Sube el `.p12` y su PIN (RF-22).

    Es `multipart` y no JSON con base64 porque es un archivo: el navegador ya
    sabe mandarlo y de paso no se infla un tercio por el camino.

    El archivo se lee entero en memoria a propósito —son unos kilobytes— y **no
    toca el disco**: un temporal con una llave privada adentro sobrevive al
    proceso que lo creó.
    """
    contenido = await archivo.read()
    return crud_fe.subir_certificado(
        db,
        ambiente,
        contenido=contenido,
        pin=pin,
        user_id=admin.user.id_user,
        company_id=admin.company_id,
    )


@router.delete("/{ambiente}/certificate", response_model=FeStatusOut)
def quitar_certificado(
    ambiente: str,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Quita el certificado y su llave (RF-24). No toca las credenciales de ATV."""
    return crud_fe.quitar_certificado(db, ambiente, company_id=admin.company_id)


@router.put("/{ambiente}/atv", response_model=FeStatusOut)
def guardar_atv(
    ambiente: str,
    payload: AtvIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Usuario y contraseña de transmisión (RF-29, RN-16).

    `PUT` y no `POST`: guardar dos veces lo mismo deja el mismo estado, y no hay
    nada que se cree ni que se acumule.
    """
    return crud_fe.guardar_atv(
        db, ambiente, payload, user_id=admin.user.id_user, company_id=admin.company_id
    )


@router.post("/{ambiente}/atv/verify", response_model=FeStatusOut)
def verificar_atv(
    ambiente: str,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Comprueba las credenciales **sin emitir nada** (RF-31).

    Es `POST` aunque parezca una consulta, y por dos razones: pide un token al
    IdP de Hacienda —un efecto afuera, que no se repite a la ligera— y escribe
    cuándo se comprobó. Un `GET` invitaría a que un navegador, un precargador o
    un reintento lo dispararan solos contra un servicio ajeno.
    """
    return crud_fe.verificar_atv(
        db, ambiente, user_id=admin.user.id_user, company_id=admin.company_id
    )


@router.put("/active", response_model=FeStatusOut)
def cambiar_ambiente(
    payload: ActiveEnvironmentIn,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Elige el ambiente en uso (RF-30, RN-35).

    Va en `/active` y no en `/{ambiente}/…` porque **el ambiente activo es uno
    solo de la compañía**, no un atributo de cada ambiente: las otras rutas
    dicen «hacé esto en pruebas» y esta dice «pasate a pruebas».
    """
    return crud_fe.cambiar_ambiente(
        db,
        payload.environment,
        confirmado=payload.confirm,
        user_id=admin.user.id_user,
        company_id=admin.company_id,
    )


# ----------------------------------------------------------- el recorrido (F7)
#
# Leer el expediente y bajar los dos XML lo puede hacer quien ve la factura
# (RF-33, RF-34): el cajero imprime la factura y tiene que poder decir en qué va.
# Reintentar es de administrador, como todo lo que escribe acá (RF-36).


@router.get("/queue", response_model=QueueOut)
def cola(
    db: Session = Depends(get_db),
    sesion: Sesion = Depends(get_current_user),
):
    """Cuántos hay en cada estado, lo detenido y la alarma de antigüedad (T-711)."""
    return crud_fe_documents.cola(db)


@router.get("/documents/{document_id}", response_model=DocumentFileOut)
def expediente(
    document_id: int,
    db: Session = Depends(get_db),
    sesion: Sesion = Depends(get_current_user),
):
    """El comprobante con su bitácora: por dónde va y a qué hora pasó cada cosa (T-721)."""
    return crud_fe_documents.expediente(db, document_id)


def _archivo(contenido: bytes, nombre: str) -> Response:
    return Response(
        content=contenido,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/documents/{document_id}/xml")
def xml_firmado(
    document_id: int,
    db: Session = Depends(get_db),
    sesion: Sesion = Depends(get_current_user),
):
    """El XML firmado **tal como se envió**, byte por byte (RF-34, RN-44)."""
    contenido, nombre = crud_fe_documents.xml_firmado(db, document_id)
    return _archivo(contenido, nombre)


@router.get("/documents/{document_id}/response")
def respuesta_de_hacienda(
    document_id: int,
    db: Session = Depends(get_db),
    sesion: Sesion = Depends(get_current_user),
):
    """La respuesta firmada de Hacienda, tal como llegó (RF-34)."""
    contenido, nombre = crud_fe_documents.respuesta_hacienda(db, document_id)
    return _archivo(contenido, nombre)


@router.post("/documents/{document_id}/retry", response_model=DocumentFileOut)
def reintentar(
    document_id: int,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """Vuelve a la cola un comprobante detenido (RF-36, RN-42)."""
    return crud_fe_documents.reintentar(
        db, document_id, user_id=admin.user.id_user, company_id=admin.company_id
    )


# ------------------------------------------- el arranque de las series (T-616)


@router.get("/sequences", response_model=SequencesOut)
def series(db: Session = Depends(get_db), admin: Sesion = Depends(require_admin)):
    """Cada caja por cada tipo encendido, con su último consecutivo (RN-37)."""
    return crud_fe_sequences.series(db)


@router.put("/sequences", response_model=SequenceStartOut)
def arrancar_serie(
    datos: SequenceStartIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    """El último consecutivo que trae un negocio de otro sistema (RF-32, RN-36 a
    RN-38). Solo sube, no se toca una serie que el sistema ya usó, y queda en
    bitácora."""
    return crud_fe_sequences.arrancar(
        db,
        datos,
        user_id=admin.user.id_user,
        ip=request.client.host if request.client else None,
    )
