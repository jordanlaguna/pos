"""
El trabajador de la cola de transmisión (T-708, T-709, plan §7.2).

Un hilo dentro del proceso de la API que, cada pocos segundos, recorre las
compañías y atiende lo que ya le toca a cada una: firmar lo numerado, enviar lo
firmado, preguntar por lo enviado. Las esperas entre intentos las decide el
dominio (`fe_transmission.py`); esto solo despierta y pregunta «¿hay algo?».

**Corre fuera de una petición**, así que no hereda compañía: abre un
`with compania(cid)` por cada una antes de tocar sus filas (T-708). Sin eso la
primera lectura lanza `SinCompania` y la cola no avanza nunca.

**Un hilo y no un proceso aparte** porque el POS de una tienda corre en un
contenedor, y agregar otro para esto es agregar algo que puede quedarse sin
arrancar. El precio es que con varios procesos de uvicorn habría varios hilos:
no pasa en este despliegue (`wait-for-db.sh` arranca uno), y si pasara, dos
turnos sobre el mismo documento se cruzan en el almacén —que se escribe una
vez— y en la clave de Hacienda —que no admite duplicados—: feo, no incorrecto.

`FE_WORKER=0` lo apaga —las pruebas que no transmiten lo apagan— y
`FE_WORKER_INTERVAL_SECONDS` dice cada cuánto despierta.
"""

from __future__ import annotations

import logging
import os
import threading

from app.database.database import SessionLocal
from app.models.model_company import Company
from app.services import crud_fe_documents
from app.utils.tenancy import compania

log = logging.getLogger("ventasys.fe")

DEFAULT_INTERVAL_SECONDS = 5.0


def enabled() -> bool:
    return os.getenv("FE_WORKER", "1").strip().lower() not in ("0", "false", "no", "off", "")


def interval_seconds() -> float:
    crudo = os.getenv("FE_WORKER_INTERVAL_SECONDS", "").strip()
    try:
        valor = float(crudo) if crudo else DEFAULT_INTERVAL_SECONDS
    except ValueError:
        valor = DEFAULT_INTERVAL_SECONDS
    return max(0.5, valor)


def companias() -> list[int]:
    """Todas. `companies` es la raíz y no lleva el filtro por compañía."""
    with SessionLocal() as db:
        return [fila.id for fila in db.query(Company.id).order_by(Company.id).all()]


def turno() -> int:
    """Un turno de la cola para todas las compañías. Cuántos documentos atendió.

    Cada compañía tiene su sesión y su contexto, y una que falle no detiene a
    las demás: lo que pasó queda en el registro del proceso.
    """
    atendidos = 0
    for cid in companias():
        with SessionLocal() as db, compania(cid):
            try:
                atendidos += crud_fe_documents.procesar_pendientes(db)
            except Exception:  # noqa: BLE001 — el hilo no puede morir por una compañía
                db.rollback()
                log.exception("cola de transmisión: compañía %s", cid)
    return atendidos


class FeWorker(threading.Thread):
    def __init__(self, interval: float) -> None:
        super().__init__(name="fe-worker", daemon=True)
        self._interval = interval
        self._stop = threading.Event()

    def run(self) -> None:
        log.info("cola de transmisión arrancada, cada %.1f s", self._interval)
        while not self._stop.is_set():
            try:
                turno()
            except Exception:  # noqa: BLE001 — ni listar compañías puede tumbarlo
                log.exception("cola de transmisión: turno fallido")
            self._stop.wait(self._interval)

    def stop(self) -> None:
        self._stop.set()


_worker: FeWorker | None = None


def start() -> FeWorker | None:
    """Arranca el hilo si está habilitado. Idempotente."""
    global _worker
    if not enabled():
        log.info("cola de transmisión apagada (FE_WORKER)")
        return None
    if _worker is not None and _worker.is_alive():
        return _worker
    _worker = FeWorker(interval_seconds())
    _worker.start()
    return _worker


def stop() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None
