"""
El catálogo CABYS de Hacienda, por HTTP.

Contrato verificado el 2026-08-16 (plan.md §6.1):

    GET https://api.hacienda.go.cr/fe/cabys?q=<texto>&top=<n>
    → { "total": 16, "cantidad": 3, "cabys": [ {...}, ... ] }

    GET https://api.hacienda.go.cr/fe/cabys?codigo=<13 dígitos>
    → [ {...} ]

**El mismo endpoint devuelve dos formas distintas**: un objeto con la lista
adentro cuando se busca por texto, y una lista pelada cuando se busca por código.
No es un descuido de este código: es cómo responde Hacienda, y por eso el lector
contempla las dos en vez de elegir una.

Se usa `urllib` de la biblioteca estándar y no un cliente HTTP nuevo: es un GET
con tiempo de espera, y el proyecto acota sus dependencias a propósito —fue
`passlib` lo que rompió una instalación entera—.

Toda falla de red sale como `CatalogUnavailable`, que el caso de uso traduce en
«respondé desde la caché y decilo» (RNF-4). Acá no se decide nada: se traduce.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation

from app.application.ports.cabys import CatalogUnavailable
from app.domain.cabys import CabysCode, InvalidCabysCode
from app.domain.errors import InvalidTaxRate
from app.domain.tax import TaxRate

BASE_URL = "https://api.hacienda.go.cr/fe/cabys"

#: Corto a propósito. Esto lo espera alguien mirando una pantalla mientras
#: clasifica un producto: cinco segundos sin respuesta ya es «no hay internet»,
#: y la caché contesta al instante.
TIMEOUT_SECONDS = 5


def _leer(url: str) -> object:
    """El JSON de una URL, o `CatalogUnavailable`.

    Se atrapa `Exception` y no solo las de `urllib` porque acá abajo cabe de
    todo —DNS, TLS, un proxy que devuelve HTML, JSON partido a la mitad— y todas
    significan lo mismo para quien llama: hoy no hay catálogo. Dejar escapar una
    convertiría una degradación prevista en un 500.
    """
    try:
        peticion = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_SECONDS) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — ver el docstring
        raise CatalogUnavailable(str(exc)) from exc


def _tarifa(crudo: object) -> TaxRate | None:
    """La tarifa de una entrada. Hacienda la manda en **porcentaje**: 13, no 0,13.

    Devuelve `None` si viene ilegible en vez de reventar: una entrada rara del
    catálogo no puede tumbar una búsqueda de veinte.
    """
    if crudo is None:
        return None
    try:
        return TaxRate(Decimal(str(crudo)) / Decimal(100))
    except (InvalidOperation, InvalidTaxRate, ValueError, TypeError):
        return None


def _entradas(datos: object) -> list[CabysCode]:
    """Las entradas de una respuesta, venga en objeto o en lista.

    Las que no se puedan leer —sin código, sin tarifa, con un código que no es de
    trece dígitos— se **descartan en silencio**. Es lo correcto para un catálogo
    ajeno: quien busca «arroz» quiere las que sirven, no un error porque la
    entrada número siete venía rara.
    """
    if isinstance(datos, dict):
        crudas = datos.get("cabys") or []
    elif isinstance(datos, list):
        crudas = datos
    else:
        crudas = []

    salida: list[CabysCode] = []
    for cruda in crudas:
        if not isinstance(cruda, dict):
            continue
        tarifa = _tarifa(cruda.get("impuesto"))
        if tarifa is None:
            continue
        try:
            salida.append(
                CabysCode(
                    code=str(cruda.get("codigo") or ""),
                    description=str(cruda.get("descripcion") or "").strip(),
                    tax_rate=tarifa,
                )
            )
        except InvalidCabysCode:
            continue
    return salida


class HaciendaCabysCatalog:
    """Cumple `CabysCatalog`."""

    def __init__(self, base_url: str = BASE_URL) -> None:
        self._base = base_url

    def search(self, text: str, limit: int) -> list[CabysCode]:
        consulta = urllib.parse.urlencode({"q": text, "top": limit})
        return _entradas(_leer(f"{self._base}?{consulta}"))[:limit]

    def by_code(self, code: str) -> CabysCode | None:
        consulta = urllib.parse.urlencode({"codigo": code})
        encontradas = _entradas(_leer(f"{self._base}?{consulta}"))
        # Se compara el código devuelto con el pedido: Hacienda podría devolver
        # coincidencias parciales, y «el código exacto» tiene que ser exacto.
        return next((e for e in encontradas if e.code == code), None)
