"""Buscar CABYS con y sin internet (T-502, T-503, RNF-4).

La regla que se fija acá: **lo que necesita internet degrada con aviso, nunca
bloquea**. Un POS en una LAN sin salida tiene que poder seguir clasificando con
lo que ya consultó, y saber que eso es lo que está viendo.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from app.application.ports.cabys import CatalogUnavailable
from app.application.use_cases.search_cabys import SearchCabys
from app.domain.cabys import CabysCode, InvalidCabysCode
from app.domain.tax import TaxRate
from app.infrastructure.clock import FixedClock

AHORA = datetime(2026, 9, 5, 12, 0, 0)
ANTES = datetime(2026, 8, 1, 9, 30, 0)

IVA = TaxRate(Decimal("0.13"))
MEDICAMENTO = TaxRate(Decimal("0.02"))

ARROZ = CabysCode("2312000000300", "Harina de arroz", IVA)
JARABE = CabysCode("3521000000100", "Jarabe para la tos", MEDICAMENTO)


class FakeCatalog:
    """Hacienda. `caido=True` es no tener internet."""

    def __init__(self, entradas=None, caido=False):
        self.entradas = entradas or []
        self.caido = caido
        self.consultas = 0

    def search(self, text, limit):
        self.consultas += 1
        if self.caido:
            raise CatalogUnavailable("sin salida")
        coincidentes = [e for e in self.entradas if text.lower() in e.description.lower()]
        return coincidentes[:limit]

    def by_code(self, code):
        self.consultas += 1
        if self.caido:
            raise CatalogUnavailable("sin salida")
        return next((e for e in self.entradas if e.code == code), None)


class FakeCache:
    def __init__(self, entradas=None, leidas_el=ANTES):
        self.entradas = list(entradas or [])
        self.leidas_el = leidas_el
        self.guardados: list[tuple] = []

    def search(self, text, limit):
        return [e for e in self.entradas if text.lower() in e.description.lower()][:limit]

    def by_code(self, code):
        return next((e for e in self.entradas if e.code == code), None)

    def updated_at(self, code):
        return self.leidas_el if self.by_code(code) else None

    def remember(self, entries, now):
        self.guardados.append((list(entries), now))
        for entrada in entries:
            self.entradas = [e for e in self.entradas if e.code != entrada.code]
            self.entradas.append(entrada)


def montar(catalogo, cache=None):
    cache = cache or FakeCache()
    return SearchCabys(catalog=catalogo, cache=cache, clock=FixedClock(AHORA)), cache


class TestConInternet:
    def test_busca_en_hacienda_y_lo_dice(self):
        caso, _ = montar(FakeCatalog([ARROZ, JARABE]))
        r = caso.by_text("arroz")

        assert [e.code for e in r.entries] == [ARROZ.code]
        assert r.source == "hacienda"
        assert r.offline is False

    def test_lo_encontrado_se_guarda_en_la_cache(self):
        """Es lo que hace que facturar no dependa de que Hacienda esté arriba:
        el código que se le asignó a un producto ya está guardado."""
        caso, cache = montar(FakeCatalog([ARROZ]))
        caso.by_text("arroz")

        assert cache.guardados == [([ARROZ], AHORA)]

    def test_por_codigo_exacto(self):
        caso, cache = montar(FakeCatalog([ARROZ, JARABE]))
        r = caso.by_code("3521000000100")

        assert [e.code for e in r.entries] == [JARABE.code]
        assert r.source == "hacienda"
        assert cache.guardados == [([JARABE], AHORA)]

    def test_un_codigo_que_hacienda_dice_que_no_existe(self):
        """No se cae a la caché: Hacienda **contestó**. La caché solo tendría lo
        que alguien buscó antes y podría contradecir al catálogo de hoy."""
        cache = FakeCache([ARROZ])
        caso, _ = montar(FakeCatalog([JARABE]), cache)
        r = caso.by_code(ARROZ.code)

        assert r.entries == []
        assert r.source == "hacienda"

    def test_el_limite_se_respeta(self):
        caso, _ = montar(FakeCatalog([ARROZ, JARABE]))
        assert len(caso.by_text("a", limit=1).entries) == 1


class TestSinInternet:
    def test_responde_desde_la_cache_y_lo_dice(self):
        caso, _ = montar(FakeCatalog(caido=True), FakeCache([ARROZ]))
        r = caso.by_text("arroz")

        assert [e.code for e in r.entries] == [ARROZ.code]
        assert r.source == "cache"
        assert r.offline is True

    def test_no_lanza_nunca_por_falta_de_internet(self):
        """Convertir una degradación prevista en un error sería bloquear al
        cajero por algo que RNF-4 dice que solo debe avisar."""
        caso, _ = montar(FakeCatalog(caido=True), FakeCache())
        r = caso.by_text("lo que sea")

        assert r.entries == []
        assert r.source == "cache"

    def test_por_codigo_dice_desde_cuando_es_lo_que_muestra(self):
        """Sin eso, quien clasifica no puede juzgar si la tarifa sigue vigente."""
        caso, _ = montar(FakeCatalog(caido=True), FakeCache([JARABE], leidas_el=ANTES))
        r = caso.by_code(JARABE.code)

        assert [e.code for e in r.entries] == [JARABE.code]
        assert r.source == "cache"
        assert r.cached_at == ANTES

    def test_un_codigo_que_no_esta_en_la_cache(self):
        caso, _ = montar(FakeCatalog(caido=True), FakeCache())
        r = caso.by_code("2312000000300")

        assert r.entries == []
        assert r.source == "cache"
        assert r.cached_at is None


class TestLoQueNoSalePreguntando:
    def test_con_texto_vacio_no_se_consulta_a_hacienda(self):
        """Cada búsqueda es un viaje a internet: no se gasta uno en nada."""
        catalogo = FakeCatalog([ARROZ])
        caso, _ = montar(catalogo)

        for vacio in ("", "   ", None):
            r = caso.by_text(vacio)
            assert r.entries == []
        assert catalogo.consultas == 0

    def test_un_codigo_mal_formado_no_llega_a_la_red(self):
        """Trece dígitos es una regla del catálogo, no algo que haya que ir a
        preguntar. Y así el «no» distingue el error de quien pide del de la red."""
        catalogo = FakeCatalog([ARROZ])
        caso, _ = montar(catalogo)

        with pytest.raises(InvalidCabysCode):
            caso.by_code("231200000030")
        assert catalogo.consultas == 0
