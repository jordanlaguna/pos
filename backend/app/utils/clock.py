"""
La hora del servidor — puente transitorio.

La implementación se mudó a `app/infrastructure/clock.py` y el contrato a
`app/application/ports/clock.py`. Este módulo queda como puente mientras los
`crud_*` siguen siendo servicios sueltos: llaman a `clock.now()` como función de
módulo, no reciben un reloj.

**Desaparece en T-108**, cuando los casos de uso reciban el `Clock` por
parámetro. Hasta entonces existe para que haya un solo lugar donde se lee la
hora, que es lo que arregló el defecto 14.
"""

from __future__ import annotations

from datetime import date, datetime

from app.infrastructure.clock import SystemClock

_reloj = SystemClock()


def now() -> datetime:
    """Hora local del servidor, al segundo. Ver `SystemClock.now`."""
    return _reloj.now()


def today() -> date:
    """Fecha de hoy según el reloj del servidor."""
    return _reloj.today()
