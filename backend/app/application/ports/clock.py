"""
El reloj, como puerto.

Existe por el defecto 9: la hora de las ventas la pone el servidor, nunca el
cliente, porque el arqueo del turno compara `sales.created_at` contra
`cash_sessions.opened_at` y dos relojes distintos no se pueden comparar.

Convertirlo en puerto agrega lo segundo que hacía falta: **poder probar un turno
de caja sin esperar en tiempo real**. Con `datetime.now()` repartido por los
servicios, comprobar que una venta de las 23:58 cae en el turno que abrió a las
22:00 exige o esperar dos horas o no probarlo. Con el reloj inyectado, se le
dice qué hora es.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol


class Clock(Protocol):
    """De dónde sale la hora."""

    def now(self) -> datetime:
        """Hora local del servidor, **al segundo**.

        Al segundo y no al microsegundo: es la resolución de las columnas
        `DATETIME` donde se guarda, y MySQL redondea al escribir. Sin truncar,
        una venta podía quedar hasta medio segundo en el futuro y desaparecer de
        su propio turno de caja (defecto 14).
        """
        ...

    def today(self) -> date:
        """Fecha de hoy según ese mismo reloj."""
        ...
