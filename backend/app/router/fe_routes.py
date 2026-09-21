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

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.schemas.schemas_fe import ActiveEnvironmentIn, AtvIn, FeStatusOut
from app.services import crud_fe
from app.utils.auth_dependency import Sesion, get_db, require_admin

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
