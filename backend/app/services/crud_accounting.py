"""Contabilidad — adaptador (T-1105).

Por ahora, lo único que hay acá es la decisión de si esta compañía lleva libros:
`libro()` devuelve el adaptador de verdad o el nulo, y es lo que permite que
`RegisterSale` y los otros cinco casos de uso no tengan un `if` de contabilidad
adentro.

Tres cosas tienen que ser ciertas a la vez para que se escriba un asiento, y las
tres se leen **en cada petición** y no del token, por lo mismo que el estado de
la suscripción (plan §4.4): en el token quedarían congeladas hasta el siguiente
login, y quien acaba de activar contabilidad tendría que salir y volver a entrar.

1. El plan de la compañía incluye el módulo (RN-49).
2. La compañía activó la contabilidad (RF-47).
3. La fecha de inicio ya pasó —eso lo comprueba el adaptador asiento por
   asiento, porque una devolución de hoy puede corresponder a una venta de
   antes (RN-60)—.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.application.ports.ledger import Ledger, NullLedger
from app.infrastructure.clock import SystemClock
from app.infrastructure.persistence.sqlalchemy_ledger import SqlAlchemyLedger
from app.services import crud_membership, crud_settings
from app.utils.tenancy import compania_actual

#: La sección de `settings.data` donde vive la configuración de contabilidad: si
#: está activa, desde cuándo y con qué plantilla se sembró. Va ahí y no en una
#: tabla propia porque es configuración de la compañía, como la moneda.
SECCION = "accounting"


def configuracion(db: Session) -> dict:
    """La sección `accounting` de la configuración, o un diccionario vacío."""
    seccion = crud_settings.get_settings(db)["data"].get(SECCION)
    return seccion if isinstance(seccion, dict) else {}


def fecha_de_inicio(config: dict) -> date | None:
    """Desde cuándo lleva libros esta compañía (RN-60).

    Una fecha ilegible se trata como «no hay fecha», que apaga el libro. Es lo
    mismo que hace la configuración con una fila corrupta: vale más un POS que
    vende sin asentar que uno que no vende.
    """
    crudo = config.get("start_date")
    if not isinstance(crudo, str):
        return None
    try:
        return date.fromisoformat(crudo)
    except ValueError:
        return None


def activa(db: Session) -> bool:
    """Si la compañía de esta petición lleva libros ahora mismo."""
    return _inicio_si_lleva_libros(db) is not None


def libro(db: Session, *, user_id: int) -> Ledger:
    """El libro de la compañía, o el nulo si no lleva.

    El nulo no es un objeto de prueba: es lo que usan casi todas las compañías,
    y no cuesta nada.
    """
    inicio = _inicio_si_lleva_libros(db)
    if inicio is None:
        return NullLedger()
    return SqlAlchemyLedger(db, user_id=user_id, start_date=inicio, clock=SystemClock())


def _inicio_si_lleva_libros(db: Session) -> date | None:
    """La fecha desde la que lleva libros, o `None` si no lleva.

    Las tres condiciones en un solo sitio: si `activa()` dijera que sí y `libro()`
    devolviera el nulo —o al revés—, la pantalla mostraría contabilidad activa y
    no se asentaría nada.
    """
    if not crud_membership.modulos_de(db, compania_actual()).includes(SECCION):
        return None
    config = configuracion(db)
    if not config.get("active"):
        return None
    return fecha_de_inicio(config)
