"""
Buscar en el catálogo CABYS, con o sin internet.

La regla de la fase, y es de RNF-4: **lo que necesita internet degrada con aviso,
nunca bloquea**. Un POS en una LAN sin salida tiene que poder seguir vendiendo, y
clasificar un producto no puede depender de que Hacienda esté arriba.

El orden es siempre el mismo:

1. Se pregunta a Hacienda.
2. Si contesta, se **guarda en la caché** y se devuelve. Eso es lo que hace que
   la siguiente vez —y el día que no haya internet— haya algo que responder.
3. Si no contesta, se responde **desde la caché** y se dice que viene de ahí,
   con la fecha de cuándo se leyó. Quien decide si eso le sirve es la persona,
   no el programa.

Nunca lanza por falta de internet: eso sería convertir una degradación en un
bloqueo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.application.ports.cabys import (
    CabysCacheRepository,
    CabysCatalog,
    CatalogUnavailable,
)
from app.application.ports.clock import Clock
from app.domain.cabys import CabysCode, normalize_code


@dataclass(frozen=True)
class CabysAnswer:
    """Lo encontrado y **de dónde salió**.

    `source` no es un detalle de implementación que se pueda esconder: es la
    diferencia entre «esto es lo que dice Hacienda hoy» y «esto es lo que decía
    la última vez que hubo internet», y quien clasifica un producto necesita
    saber cuál de las dos está leyendo.
    """

    entries: list[CabysCode]
    #: 'hacienda' | 'cache'
    source: str
    #: Cuándo se leyó de Hacienda lo que se está devolviendo. Solo con 'cache':
    #: con 'hacienda' es ahora mismo y no aporta nada.
    cached_at: datetime | None = None

    @property
    def offline(self) -> bool:
        return self.source == "cache"


class SearchCabys:
    def __init__(
        self,
        *,
        catalog: CabysCatalog,
        cache: CabysCacheRepository,
        clock: Clock,
    ) -> None:
        self._catalog = catalog
        self._cache = cache
        self._clock = clock

    def by_text(self, text: str, limit: int = 20) -> CabysAnswer:
        """Busca por descripción. Con texto vacío no se pregunta nada."""
        limpio = (text or "").strip()
        if not limpio:
            return CabysAnswer(entries=[], source="hacienda")

        try:
            encontrados = self._catalog.search(limpio, limit)
        except CatalogUnavailable:
            return CabysAnswer(entries=self._cache.search(limpio, limit), source="cache")

        self._cache.remember(encontrados, self._clock.now())
        return CabysAnswer(entries=encontrados, source="hacienda")

    def by_code(self, raw_code: str) -> CabysAnswer:
        """Un código exacto. Valida el formato antes de salir a la red: trece
        dígitos es una regla del catálogo, no algo que haya que ir a preguntar."""
        code = normalize_code(raw_code)

        try:
            encontrado = self._catalog.by_code(code)
        except CatalogUnavailable:
            desde_cache = self._cache.by_code(code)
            return CabysAnswer(
                entries=[desde_cache] if desde_cache else [],
                source="cache",
                cached_at=self._cache.updated_at(code) if desde_cache else None,
            )

        if encontrado is None:
            # Hacienda contestó y dijo que no existe. Es una respuesta, no una
            # falla: no se cae a la caché, que solo tendría lo que alguien buscó
            # antes y podría contradecir al catálogo de hoy.
            return CabysAnswer(entries=[], source="hacienda")

        self._cache.remember([encontrado], self._clock.now())
        return CabysAnswer(entries=[encontrado], source="hacienda")
