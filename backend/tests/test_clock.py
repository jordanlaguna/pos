"""
El reloj: el adaptador de sistema y su doble.

Es código puro: no necesita la pila de pruebas ni la base. Corre siempre.
"""

from __future__ import annotations

import time
from datetime import date, datetime

from app.application.ports.clock import Clock
from app.infrastructure.clock import FixedClock, SystemClock
from app.utils import clock


class TestSystemClock:
    def test_cumple_el_puerto(self):
        # `Clock` es un Protocol: se cumple por tener los métodos, sin heredar.
        reloj: Clock = SystemClock()
        assert isinstance(reloj.now(), datetime)
        assert isinstance(reloj.today(), date)

    def test_devuelve_la_hora_actual(self):
        antes = datetime.now().replace(microsecond=0)
        valor = SystemClock().now()
        assert antes <= valor <= datetime.now()

    def test_no_lleva_microsegundos(self):
        """
        Defecto 14. Las columnas de fecha son `DATETIME` sin fracción, y MySQL
        **redondea** al guardar: `10:00:05.700` termina almacenado como
        `10:00:06`, medio segundo en el futuro. El arqueo delimita las ventas
        del turno con `created_at <= ahora`, así que una venta con marca futura
        quedaba fuera de su propio turno.

        Sin esta línea el defecto vuelve, y vuelve de forma intermitente, que es
        la peor manera de volver.
        """
        reloj = SystemClock()
        for _ in range(50):
            assert reloj.now().microsecond == 0

    def test_nunca_queda_por_delante_del_reloj_del_sistema(self):
        """Lo mismo dicho como relación, que es lo que el arqueo necesita."""
        reloj = SystemClock()
        for _ in range(50):
            assert reloj.now() <= datetime.now()

    def test_avanza(self):
        reloj = SystemClock()
        primero = reloj.now()
        time.sleep(1.05)
        assert reloj.now() > primero

    def test_today_es_la_fecha_de_now(self):
        reloj = SystemClock()
        assert reloj.today() == reloj.now().date()


class TestFixedClock:
    """El doble que hace posible probar un turno sin esperar en tiempo real."""

    def test_marca_lo_que_se_le_diga(self):
        reloj = FixedClock(datetime(2026, 8, 16, 22, 0, 0))
        assert reloj.now() == datetime(2026, 8, 16, 22, 0, 0)
        assert reloj.today() == date(2026, 8, 16)

    def test_no_se_mueve_solo(self):
        reloj = FixedClock(datetime(2026, 8, 16, 22, 0, 0))
        assert reloj.now() == reloj.now()

    def test_trunca_igual_que_el_de_verdad(self):
        reloj = FixedClock(datetime(2026, 8, 16, 22, 0, 0, 700_000))
        assert reloj.now().microsecond == 0

    def test_se_le_puede_cambiar_la_hora(self):
        reloj = FixedClock(datetime(2026, 8, 16, 22, 0, 0))
        reloj.set(datetime(2026, 8, 16, 23, 58, 0, 900_000))
        assert reloj.now() == datetime(2026, 8, 16, 23, 58, 0)

    def test_se_le_puede_adelantar(self):
        # El turno abre a las 22:00 y la venta ocurre a las 23:58, sin esperar
        # dos horas de verdad.
        reloj = FixedClock(datetime(2026, 8, 16, 22, 0, 0))
        apertura = reloj.now()
        reloj.advance(hours=1, minutes=58)
        assert reloj.now() > apertura
        assert reloj.now() == datetime(2026, 8, 16, 23, 58, 0)

    def test_cumple_el_puerto(self):
        reloj: Clock = FixedClock(datetime(2026, 1, 1))
        assert isinstance(reloj.now(), datetime)
        assert isinstance(reloj.today(), date)


class TestPuenteTransitorio:
    """`app/utils/clock.py` sigue en pie mientras los crud_* no reciban reloj."""

    def test_delega_en_el_adaptador(self):
        assert clock.now().microsecond == 0
        assert clock.today() == clock.now().date()
