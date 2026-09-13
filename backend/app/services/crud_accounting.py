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

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.application.ports.ledger import Ledger, NullLedger
from app.application.use_cases.accounting import (
    ActivateAccounting,
    ActivationRequest,
    AlreadyActive,
    OpeningLine,
)
from app.domain.chart import CHART, COMMERCE, TEMPLATES
from app.domain.errors import EntryNotBalanced
from app.domain.money import Money
from app.infrastructure.clock import SystemClock
from app.infrastructure.persistence.sqlalchemy_accounting import (
    SqlAlchemyAccountingSettings,
    SqlAlchemyAccountRepository,
    SqlAlchemyMappingRepository,
    SqlAlchemyPeriodRepository,
)
from app.infrastructure.persistence.sqlalchemy_ledger import SqlAlchemyLedger
from app.infrastructure.persistence.sqlalchemy_repositories import SqlAlchemyUnitOfWork
from app.services import crud_membership, crud_settings
from app.utils.api_errors import api_error
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


def estado(db: Session) -> dict:
    """Qué sabe el POS de la contabilidad de esta compañía.

    Va la plantilla entera aunque no esté activa: es lo que la pantalla de
    activación necesita para ofrecer los saldos iniciales, y antes de activar no
    hay ninguna cuenta que listar.
    """
    config = configuracion(db)
    return {
        "active": bool(config.get("active")),
        "template": config.get("template"),
        "start_date": config.get("start_date"),
        "templates": list(TEMPLATES),
        "chart": [
            {
                "code": cuenta.code,
                "name": cuenta.name,
                "kind": cuenta.kind,
                "is_system": cuenta.is_system,
            }
            for cuenta in CHART
        ],
    }


def activar(db: Session, payload, *, user_id: int) -> dict:
    """`POST /accounting/activate` (RF-47)."""
    inicio = payload.start_date
    caso = ActivateAccounting(
        accounts=SqlAlchemyAccountRepository(db),
        mappings=SqlAlchemyMappingRepository(db),
        periods=SqlAlchemyPeriodRepository(db),
        settings=SqlAlchemyAccountingSettings(db),
        # El libro se arma a mano y no con `libro()`: esa fábrica lee la
        # configuración, que todavía dice que la contabilidad no está activa, y
        # devolvería el nulo. El asiento de apertura se perdería sin un solo
        # error, que es la peor forma de perderse.
        journal=SqlAlchemyLedger(db, user_id=user_id, start_date=inicio, clock=SystemClock()),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
    )

    try:
        resultado = caso(
            ActivationRequest(
                template=payload.template or COMMERCE,
                start_date=inicio,
                user_id=user_id,
                opening=tuple(
                    OpeningLine(
                        account_code=linea.account_code,
                        debit=Money(linea.debit),
                        credit=Money(linea.credit),
                    )
                    for linea in (payload.opening or [])
                ),
                description=payload.description or "",
            )
        )
    except AlreadyActive:
        raise api_error(400, "accounting_already_active") from None
    except EntryNotBalanced as e:
        raise api_error(
            400, "invalid_opening_balance", debits=e.debits, credits=e.credits
        ) from None
    except HTTPException:
        raise
    except Exception as exc:
        # `UnknownTemplate` y `UnknownAccountCode` caen acá y no tienen código
        # propio a propósito: el esquema ya los rechaza con el 422 de un cuerpo
        # mal formado, porque la pantalla arma el formulario con la misma
        # plantilla que el servidor le dio. Llegar hasta acá significa que algo
        # más se rompió, y entonces no hay activación a medias: la unidad de
        # trabajo ya revirtió.
        raise api_error(500, "accounting_failed", cause=str(exc)) from None

    return {
        "accounts_created": resultado.accounts_created,
        "mappings_created": resultado.mappings_created,
        "opening_entry_id": resultado.opening_entry_id,
        **estado(db),
    }


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
