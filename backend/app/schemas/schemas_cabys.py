"""Contrato del proxy de CABYS."""

import datetime

from pydantic import BaseModel


class CabysItem(BaseModel):
    code: str
    description: str
    #: Entre 0 y 1, como toda tasa del sistema: el 13 % es 0.13. Hacienda la
    #: publica en porcentaje y la traducción vive en el adaptador.
    tax_rate: float


class CabysSearchResponse(BaseModel):
    """Lo encontrado y **de dónde salió**.

    `source` no es un detalle interno: es la diferencia entre «esto dice Hacienda
    hoy» y «esto decía la última vez que hubo internet». Quien clasifica un
    producto necesita saber cuál está leyendo, así que viaja siempre (RNF-4).
    """

    #: 'hacienda' | 'cache'
    source: str
    #: Cuándo se leyó de Hacienda lo que se devuelve. Solo con `source: cache`.
    cached_at: datetime.datetime | None = None
    items: list[CabysItem] = []
