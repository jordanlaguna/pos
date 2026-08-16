import datetime

from pydantic import BaseModel, Field


class Logo(BaseModel):
    """Imagen de marca, embebida en base64.

    Se guarda en la base y no en disco a propósito: el backend corre en un
    contenedor y un archivo suelto se pierde en el siguiente `docker compose up
    --build`. Además así el logo viaja con el respaldo de la base, que es lo que
    el dueño del negocio va a copiar cuando cambie de servidor.
    """

    # Solo formatos de mapa de bits. SVG queda fuera adrede: es XML, puede traer
    # <script>, y este logo se sirve tal cual al navegador.
    mime: str = Field(pattern=r"^image/(png|jpeg|webp)$")
    # base64 sin el prefijo `data:`; ~340 KB permiten una imagen de 250 KB.
    data: str = Field(max_length=350_000)


class SettingsResponse(BaseModel):
    data: dict = {}
    logo: Logo | None = None
    updated_at: datetime.datetime | None = None
    updated_by: int | None = None


class SettingsUpdate(BaseModel):
    """Configuración completa: lo que se manda reemplaza a lo que había.

    `data` viaja sin esquema fijo (ver la nota de model_settings). El backend
    solo comprueba que sea un objeto de tamaño razonable y que el impuesto, si
    viene, sea una tasa creíble: es el único campo que este servicio lee por su
    cuenta, al calcular devoluciones.
    """

    data: dict
    # null = borrar el logo; ausente = dejar el que estaba.
    logo: Logo | None = None
    keep_logo: bool = True
