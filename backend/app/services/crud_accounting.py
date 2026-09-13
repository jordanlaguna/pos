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
    AccountNotFound,
    ActivateAccounting,
    ActivationRequest,
    AlreadyActive,
    ClosePeriod,
    JournalEntryNotFound,
    ManualEntryRequest,
    ManualLine,
    MissingDescription,
    OpeningLine,
    PeriodNotFound,
    Reclassify,
    ReclassifyRequest,
    RecordManualEntry,
)
from app.domain.chart import (
    CHART,
    COMMERCE,
    TEMPLATES,
    UNMAPPED_ON_PURPOSE,
    check_deactivatable,
    check_deletable,
    default_mapping,
)
from app.domain.errors import (
    AccountInUse,
    AccountIsSystem,
    EntryNotBalanced,
    InvalidJournalLine,
    NothingToReclassify,
    PeriodClosed,
    PeriodNotCloseable,
)
from app.domain.money import Money
from app.infrastructure.clock import SystemClock
from app.infrastructure.persistence.sqlalchemy_accounting import (
    SqlAlchemyAccountingSettings,
    SqlAlchemyAccountRepository,
    SqlAlchemyJournalRepository,
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


# ---------------------------------------------------------------- el catálogo


def _cuenta(fila) -> dict:
    return {
        "id": fila.id,
        "code": fila.code,
        "name": fila.name,
        "kind": fila.kind,
        "parent_id": fila.parent_id,
        "is_system": bool(fila.is_system),
        "is_active": bool(fila.is_active),
    }


def cuentas(db: Session) -> list[dict]:
    """El catálogo, ordenado por código (RF-48)."""
    return [_cuenta(fila) for fila in SqlAlchemyAccountRepository(db).all()]


def crear_cuenta(db: Session, payload) -> dict:
    """Una cuenta nueva del contador. Nunca de sistema: esas son de la plantilla."""
    repositorio = SqlAlchemyAccountRepository(db)
    if repositorio.by_code(payload.code) is not None:
        raise api_error(400, "account_code_taken", account_code=payload.code)

    madre = None
    if payload.parent_id is not None:
        madre = repositorio.get(payload.parent_id)
        if madre is None:
            raise api_error(404, "account_not_found", account_id=payload.parent_id)

    id_cuenta = repositorio.create(
        code=payload.code,
        name=payload.name,
        kind=payload.kind,
        parent_id=madre.id if madre else None,
        # Solo la plantilla crea cuentas de sistema. Si el usuario pudiera
        # marcarlas, se estaría dando a sí mismo una cuenta que después no puede
        # borrar, y RN-64 dejaría de significar «la necesita el mapeo».
        is_system=False,
    )
    db.commit()
    return _cuenta(repositorio.get(id_cuenta))


def actualizar_cuenta(db: Session, account_id: int, payload) -> dict:
    """Renombrar, y activar o desactivar (RF-48, RN-64)."""
    repositorio = SqlAlchemyAccountRepository(db)
    fila = repositorio.get(account_id)
    if fila is None:
        raise api_error(404, "account_not_found", account_id=account_id)

    if payload.is_active is False:
        try:
            check_deactivatable(fila.code, is_system=bool(fila.is_system))
        except AccountIsSystem as e:
            raise api_error(400, "account_is_system", account_code=e.code) from None

    repositorio.update(fila, name=payload.name, is_active=payload.is_active)
    db.commit()
    return _cuenta(repositorio.get(account_id))


def borrar_cuenta(db: Session, account_id: int) -> dict:
    """Borrar, solo si nunca tuvo movimientos y no es de sistema (RN-64)."""
    repositorio = SqlAlchemyAccountRepository(db)
    fila = repositorio.get(account_id)
    if fila is None:
        raise api_error(404, "account_not_found", account_id=account_id)

    try:
        check_deletable(
            fila.code,
            is_system=bool(fila.is_system),
            lines=repositorio.lines_for(account_id),
        )
    except AccountIsSystem as e:
        raise api_error(400, "account_is_system", account_code=e.code) from None
    except AccountInUse as e:
        # Con movimientos no se borra: se desactiva. Va la cuenta de líneas
        # porque quien lo lee necesita saber que hay historia detrás.
        raise api_error(
            400, "account_in_use", account_code=e.code, lines=e.lines
        ) from None

    repositorio.delete(fila)
    db.commit()
    return {"deleted": account_id}


# ------------------------------------------------------------------- el mapeo


def mapeo(db: Session) -> dict:
    """Qué cuenta usa cada papel, y **qué falta** (RF-49).

    La lista sale de los papeles que el sistema puede pedir, no de las filas que
    haya: una fila que falta es justo lo que hay que ver en rojo, y si la lista
    saliera de la tabla, lo que falta no aparecería nunca.
    """
    puestas = {
        (evento, papel): cid
        for evento, papel, cid in SqlAlchemyMappingRepository(db).all()
    }
    por_id = {fila.id: fila for fila in SqlAlchemyAccountRepository(db).all()}

    papeles: list[tuple[str, str, bool]] = [
        (evento, papel, False) for evento, papel in default_mapping()
    ]
    papeles += [
        (evento, papel, True)
        for evento, sueltos in UNMAPPED_ON_PURPOSE.items()
        for papel in sueltos
    ]

    filas = []
    for evento, papel, a_proposito in sorted(papeles):
        cuenta = por_id.get(puestas.get((evento, papel)))
        filas.append(
            {
                "event": evento,
                "role": papel,
                "account_id": cuenta.id if cuenta else None,
                "account_code": cuenta.code if cuenta else None,
                "account_name": cuenta.name if cuenta else None,
                # Los que caen en «por clasificar» a propósito no se pintan en
                # rojo: no están mal, es que el sistema no sabe (plan §13.8).
                "unmapped_on_purpose": a_proposito,
            }
        )
    return {"mappings": filas}


def guardar_mapeo(db: Session, payload) -> dict:
    """Cambia las cuentas del mapeo (RF-49, RN-62).

    Afecta lo que venga y nunca lo que ya está en el libro: los asientos
    guardaron el id de la cuenta, no el papel.
    """
    repositorio = SqlAlchemyAccountRepository(db)
    mapas = SqlAlchemyMappingRepository(db)
    for fila in payload.mappings or []:
        cuenta = repositorio.get(fila.account_id)
        if cuenta is None or not cuenta.is_active:
            # Una inactiva se trata como inexistente: no se ofrece para escribir,
            # y mapear un papel ahí escondería el saldo en una cuenta que la
            # pantalla ya no muestra.
            raise api_error(404, "account_not_found", account_id=fila.account_id)
        mapas.set(event=fila.event, role=fila.role, account_id=fila.account_id)

    db.commit()
    return mapeo(db)


# -------------------------------------------------------------- reclasificar


def reclasificar(db: Session, entry_id: int, payload, *, user_id: int) -> dict:
    """Saca de «por clasificar» lo que cayó ahí (RF-49, RN-59)."""
    caso = Reclassify(
        entries=SqlAlchemyJournalRepository(db),
        accounts=SqlAlchemyAccountRepository(db),
        journal=libro(db, user_id=user_id),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
    )

    try:
        id_ajuste = caso(
            ReclassifyRequest(
                entry_id=entry_id,
                to_account_id=payload.account_id,
                user_id=user_id,
                description=payload.description or "",
            )
        )
    except JournalEntryNotFound:
        raise api_error(404, "journal_entry_not_found", entry_id=entry_id) from None
    except AccountNotFound as e:
        raise api_error(404, "account_not_found", account_id=e.account_id) from None
    except NothingToReclassify:
        raise api_error(400, "nothing_to_reclassify", entry_id=entry_id) from None
    except PeriodClosed as e:
        raise api_error(400, "period_closed", year=e.year, month=e.month) from None

    return {"adjustment_entry_id": id_ajuste}


# --------------------------------------------------------------- los asientos


def _money(valor) -> float:
    return float(valor or 0)


def _asiento(fila, lineas=None) -> dict:
    salida = {
        "id": fila.id,
        "entry_number": fila.entry_number,
        "entry_date": fila.entry_date,
        "kind": fila.kind,
        "source_type": fila.source_type,
        "source_id": fila.source_id,
        "adjusts_entry_id": fila.adjusts_entry_id,
        # En los automáticos es el código del evento y en los manuales, la frase
        # de quien lo dictó. El POS decide cuál muestra (RN-30).
        "description": fila.description,
        "user_id": fila.user_id,
        "created_at": fila.created_at,
    }
    if lineas is not None:
        salida["lines"] = lineas
        salida["total"] = round(sum(l["debit"] for l in lineas), 2)
    return salida


def asientos(db: Session, *, year: int | None, month: int | None, kind: str | None) -> list[dict]:
    """El libro diario del periodo que se pida (RF-53)."""
    return [
        _asiento(fila)
        for fila in SqlAlchemyJournalRepository(db).en_el_mes(
            year=year, month=month, kind=kind
        )
    ]


def asiento(db: Session, entry_id: int) -> dict:
    """Un asiento con sus líneas y el nombre de cada cuenta."""
    repositorio = SqlAlchemyJournalRepository(db)
    fila = repositorio.get(entry_id)
    if fila is None:
        raise api_error(404, "journal_entry_not_found", entry_id=entry_id)

    lineas = [
        {
            "account_id": cuenta.id,
            "account_code": cuenta.code,
            "account_name": cuenta.name,
            "debit": _money(linea.debit),
            "credit": _money(linea.credit),
            # En porcentaje, como se guarda y como lo lee un contador.
            "tax_rate": float(linea.tax_rate) if linea.tax_rate is not None else None,
            "memo": linea.memo,
        }
        for linea, cuenta in repositorio.filas_con_cuenta(entry_id)
    ]
    return _asiento(fila, lineas)


def crear_asiento(db: Session, payload, *, user_id: int) -> dict:
    """Un asiento manual o de ajuste (RF-51)."""
    caso = RecordManualEntry(
        accounts=SqlAlchemyAccountRepository(db),
        journal=libro(db, user_id=user_id),
        uow=SqlAlchemyUnitOfWork(db),
    )

    try:
        id_asiento = caso(
            ManualEntryRequest(
                entry_date=payload.entry_date,
                description=payload.description or "",
                kind=payload.kind,
                adjusts_entry_id=payload.adjusts_entry_id,
                user_id=user_id,
                lines=tuple(
                    ManualLine(
                        account_id=linea.account_id,
                        debit=Money(linea.debit),
                        credit=Money(linea.credit),
                        memo=linea.memo,
                    )
                    for linea in (payload.lines or [])
                ),
            )
        )
    except MissingDescription:
        raise api_error(400, "journal_missing_description") from None
    except AccountNotFound as e:
        raise api_error(404, "account_not_found", account_id=e.account_id) from None
    except InvalidJournalLine as e:
        raise api_error(400, "invalid_journal_line", reason=e.code) from None
    except EntryNotBalanced as e:
        raise api_error(
            400, "entry_not_balanced", debits=e.debits, credits=e.credits
        ) from None
    except PeriodClosed as e:
        raise api_error(400, "period_closed", year=e.year, month=e.month) from None

    if id_asiento is None:
        # El libro nulo, o una fecha anterior al arranque de la contabilidad
        # (RN-60). Las dos cosas significan lo mismo: acá no hay libro donde
        # escribir esto.
        raise api_error(400, "accounting_not_active")

    return asiento(db, id_asiento)


# --------------------------------------------------------------- los periodos


def _periodo(fila) -> dict:
    return {
        "id": fila.id,
        "year": fila.year,
        "month": fila.month,
        "status": fila.status,
        "closed_at": fila.closed_at,
        "closed_by": fila.closed_by,
    }


def periodos(db: Session) -> list[dict]:
    """Los meses, del más nuevo al más viejo (RF-52)."""
    return [_periodo(fila) for fila in SqlAlchemyPeriodRepository(db).all()]


def cerrar_periodo(db: Session, year: int, month: int, *, sesion) -> dict:
    """Cierra el mes y lo deja en bitácora (RF-52, RN-61).

    Las dos cosas en la misma transacción, por lo mismo que la anulación de una
    compra: un cierre sin su registro es exactamente lo que la bitácora existe
    para que no pase, y cerrar no se deshace.
    """
    uow = SqlAlchemyUnitOfWork(db)
    caso = ClosePeriod(
        periods=SqlAlchemyPeriodRepository(db), uow=uow, clock=SystemClock()
    )

    try:
        with uow:
            fila = caso.apply(year=year, month=month, user_id=sesion.user.id_user)
            resultado = _periodo(fila)
            crud_membership.registrar(
                db,
                user_id=sesion.user.id_user,
                company_id=sesion.company_id,
                accion="cerrar_periodo",
                detalle=f"{year}-{month:02d}",
            )
            uow.commit()
    except PeriodNotFound:
        raise api_error(404, "period_not_found", year=year, month=month) from None
    except PeriodClosed:
        raise api_error(400, "period_closed", year=year, month=month) from None
    except PeriodNotCloseable as e:
        raise api_error(
            400,
            "period_not_closeable",
            year=e.year,
            month=e.month,
            blocking_year=e.blocking_year,
            blocking_month=e.blocking_month,
        ) from None

    # El resumen se arma **antes** del `commit`: después, SQLAlchemy expira los
    # objetos y releer un atributo dispara una consulta que ya no tiene compañía.
    return resultado
