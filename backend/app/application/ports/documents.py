"""
El almacén de comprobantes (T-623, plan §7.3).

Guarda los cinco tipos de documento que hay que custodiar: el XML firmado que se
le manda a Hacienda, la respuesta firmada de la autoridad, y el comprobante, el
acuse y el PDF de los que llegan de un proveedor.

**Recibe un `DocumentRef`, no una ruta.** El dominio arma el nombre y este
puerto lo obedece, así que no hay ningún punto del programa donde alguien pueda
componer una ruta a mano y equivocarse de compañía.

**No hay `delete`, y la ausencia es la decisión.** Estos documentos se custodian
por ley durante años; borrar uno no es una operación de la aplicación sino una
tarea de mantenimiento con su propio plazo y su propia autorización. Un método
en el puerto sería una invitación a llamarlo desde un caso de uso.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.fe_documents import DocumentRef


class StorageUnavailable(Exception):
    """No se pudo hablar con el almacén.

    Es el estado del que hay que poder salir sin perder nada: quien la atrapa
    **no** confirma la transacción. Un comprobante cuyo XML no se guardó es un
    comprobante que no se puede volver a presentar, y eso es peor que no
    haberlo emitido todavía.
    """


class DocumentAlreadyStored(Exception):
    """Ya hay algo con ese nombre, y no se pisa.

    Un XML firmado que cambia deja de ser el que se firmó —la firma no
    verificaría— y la respuesta de Hacienda para una clave es final: un
    comprobante rechazado se corrige emitiendo **otra** clave, no reescribiendo
    esta. El caso real que esto ataja es un reintento de la cola que llega tarde
    y pisa el acuse bueno con uno viejo.
    """

    def __init__(self, key: str) -> None:
        super().__init__(f"ya hay un documento guardado en {key}")
        self.key = key


class DocumentNotFound(Exception):
    """No hay nada con ese nombre."""

    def __init__(self, key: str) -> None:
        super().__init__(f"no hay documento en {key}")
        self.key = key


class DocumentStore(Protocol):
    """Dónde quedan los comprobantes."""

    def put(self, ref: DocumentRef, content: bytes) -> str:
        """Guarda el documento y devuelve su ruta.

        Se escribe **una sola vez**: si ya hay algo con ese nombre lanza
        `DocumentAlreadyStored` en vez de reemplazarlo.
        """
        ...

    def get(self, ref: DocumentRef) -> bytes:
        """Lo devuelve byte por byte, o `DocumentNotFound`.

        Que sea byte por byte no es una obviedad: es la propiedad de la que
        depende que una firma todavía verifique cinco años después.
        """
        ...

    def exists(self, ref: DocumentRef) -> bool:
        """Si está guardado. No lo baja."""
        ...
