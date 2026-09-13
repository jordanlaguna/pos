"""
El almacén de comprobantes, contra S3 (T-623, plan §7.3).

Habla la API de S3 y no la de MinIO. En la VM de un negocio del otro lado hay un
MinIO en su contenedor; en un despliegue hospedado puede haber S3, R2 o
Backblaze, y este archivo no se entera. Atarse al cliente de MinIO habría sido
elegir el proveedor desde el código.

Verificado contra MinIO `RELEASE.2025-09-07` el 2026-09-13: con
`IfNoneMatch="*"` la segunda escritura de la misma llave devuelve
`PreconditionFailed` (412) y **el contenido original no se toca**. Eso es lo que
convierte «se escribe una vez» en una garantía del almacén en vez de un
`head_object` antes del `put`, que tiene carrera: entre la consulta y la
escritura cabe otro proceso.

Acá no se decide nada de negocio —la ruta la arma el dominio— y no se escribe
ningún texto para personas: se traduce lo que responde S3 a las excepciones del
puerto.
"""

from __future__ import annotations

import os

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.application.ports.documents import (
    DocumentAlreadyStored,
    DocumentNotFound,
    StorageUnavailable,
)
from app.domain.fe_documents import DocumentRef

#: Lo que S3 y MinIO contestan cuando `IfNoneMatch="*"` no se cumple. Se miran
#: las dos formas porque el código textual no está garantizado entre
#: implementaciones y el 412 sí.
_YA_EXISTE = {"PreconditionFailed", "412"}

#: Lo que contestan cuando no hay nada con ese nombre. `head_object` devuelve
#: `404` a secas y `get_object` devuelve `NoSuchKey`: son el mismo hecho dicho
#: por dos operaciones distintas de la misma API.
_NO_ESTA = {"NoSuchKey", "NoSuchBucket", "404"}

#: Corto: quien espera esto es una transacción abierta, no una persona mirando
#: una pantalla. Si el almacén no contesta, lo que hay que hacer es no confirmar.
TIMEOUT_SECONDS = 10


def _codigo(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))


class S3DocumentStore:
    """Implementa `DocumentStore` contra cualquier almacén compatible con S3."""

    def __init__(self, client, bucket: str) -> None:
        self._s3 = client
        self._bucket = bucket

    # ------------------------------------------------------------- escritura

    def put(self, ref: DocumentRef, content: bytes) -> str:
        llave = ref.key
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=llave,
                Body=content,
                ContentType=ref.content_type,
                IfNoneMatch="*",
            )
        except ClientError as exc:
            if _codigo(exc) in _YA_EXISTE:
                raise DocumentAlreadyStored(llave) from exc
            raise StorageUnavailable(str(exc)) from exc
        except BotoCoreError as exc:
            # Red, DNS, tiempo de espera. Para quien llama significan lo mismo
            # que un 500 del almacén: no confirmar.
            raise StorageUnavailable(str(exc)) from exc
        return llave

    # ---------------------------------------------------------------- lectura

    def get(self, ref: DocumentRef) -> bytes:
        llave = ref.key
        try:
            respuesta = self._s3.get_object(Bucket=self._bucket, Key=llave)
            return respuesta["Body"].read()
        except ClientError as exc:
            if _codigo(exc) in _NO_ESTA:
                raise DocumentNotFound(llave) from exc
            raise StorageUnavailable(str(exc)) from exc
        except BotoCoreError as exc:
            raise StorageUnavailable(str(exc)) from exc

    def exists(self, ref: DocumentRef) -> bool:
        try:
            self._s3.head_object(Bucket=self._bucket, Key=ref.key)
            return True
        except ClientError as exc:
            if _codigo(exc) in _NO_ESTA:
                return False
            raise StorageUnavailable(str(exc)) from exc
        except BotoCoreError as exc:
            raise StorageUnavailable(str(exc)) from exc


# ------------------------------------------------------------------- armado


def s3_client(
    *, endpoint: str, access_key: str, secret_key: str, region: str = "us-east-1"
):
    """Un cliente de S3 apuntado a donde diga la configuración.

    `addressing_style="path"` es obligatorio contra MinIO: el estilo por
    omisión pone el bucket en el nombre del servidor —`bucket.minio:9000`— y ahí
    no hay DNS que lo resuelva dentro de una red de Compose.
    """
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=TIMEOUT_SECONDS,
            read_timeout=TIMEOUT_SECONDS,
            retries={"max_attempts": 2},
        ),
    )


def ensure_bucket(client, bucket: str) -> None:
    """Lo crea si no está. Idempotente a propósito: lo llama el arranque.

    Un despliegue nuevo no debería necesitar que alguien entre a la consola de
    MinIO a crear un bucket antes de poder facturar.
    """
    try:
        client.head_bucket(Bucket=bucket)
        return
    except ClientError as exc:
        if _codigo(exc) not in _NO_ESTA:
            raise StorageUnavailable(str(exc)) from exc
    except BotoCoreError as exc:
        raise StorageUnavailable(str(exc)) from exc

    try:
        client.create_bucket(Bucket=bucket)
    except ClientError as exc:
        # Dos procesos arrancando a la vez: el segundo se encuentra con el
        # bucket que acaba de crear el primero, y eso no es un error.
        if _codigo(exc) not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
            raise StorageUnavailable(str(exc)) from exc
    except BotoCoreError as exc:
        raise StorageUnavailable(str(exc)) from exc


def document_store() -> S3DocumentStore:
    """El almacén que dice la configuración, con su bucket ya creado."""
    bucket = os.getenv("FE_STORAGE_BUCKET", "ventasys-fe")
    cliente = s3_client(
        endpoint=os.getenv("FE_STORAGE_ENDPOINT", "http://minio:9000"),
        access_key=os.getenv("FE_STORAGE_ACCESS_KEY", ""),
        secret_key=os.getenv("FE_STORAGE_SECRET_KEY", ""),
    )
    ensure_bucket(cliente, bucket)
    return S3DocumentStore(cliente, bucket)
