"""
El reloj de verdad y su doble.

`SystemClock` es el que corre en producción; `FixedClock` es el que hace
posible probar un turno de caja sin esperar dos horas. Los dos cumplen el puerto
`application.ports.clock.Clock` sin heredar de nada: es un `Protocol`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta


class SystemClock:
    """La hora del servidor donde corre la API."""

    def now(self) -> datetime:
        """
        Hora local, truncada al segundo.

        El truncado es el defecto 14. Las columnas de fecha son `DATETIME` sin
        fracción, y MySQL **redondea** al guardar: `10:00:05.700` termina
        almacenado como `10:00:06`. Python escribe con microsegundos, así que
        una venta podía quedar guardada hasta medio segundo por delante del
        reloj. El arqueo delimita el turno con `created_at <= ahora`, y una
        venta con marca futura no entra en esa ventana: desaparecía de su propio
        turno. Si además la caja se cerraba en ese medio segundo, no aparecía en
        ninguno.

        Truncar acá hace que lo guardado nunca sea posterior a lo ocurrido, que
        es la única relación que el arqueo necesita para ser correcto.
        """
        return datetime.now().replace(microsecond=0)

    def today(self) -> date:
        return self.now().date()


class FixedClock:
    """
    Un reloj que marca lo que se le diga.

    Para las pruebas: deja comprobar que una venta de las 23:58 cae dentro del
    turno que abrió a las 22:00 sin esperar dos horas, y que una de las 21:59 no.
    """

    def __init__(self, moment: datetime) -> None:
        self._moment = moment.replace(microsecond=0)

    def now(self) -> datetime:
        return self._moment

    def today(self) -> date:
        return self._moment.date()

    # ------------------------------------------------------------ manejarlo

    def set(self, moment: datetime) -> None:
        self._moment = moment.replace(microsecond=0)

    def advance(self, **delta) -> None:
        """`reloj.advance(hours=2)` — mueve el reloj hacia adelante."""
        self._moment = self._moment + timedelta(**delta)
