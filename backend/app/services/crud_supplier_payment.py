"""Abonos a proveedor — adaptador.

Las reglas están en `app/domain/purchases.py` y el paso a paso en
`app/application/use_cases/supplier_payment.py`. Acá queda la traducción a HTTP,
en código y datos, nunca en frases (RN-30).
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.application.use_cases.cash_session import (
    AddCashMovement,
    BuildSessionReport,
    NoOpenSession,
)
from app.application.use_cases.supplier_payment import (
    PaymentRequest,
    PaySupplier,
    PurchaseCancelled,
    PurchaseNotFound,
)
from app.domain.errors import InsufficientCash, InvalidMovement, InvalidPayment, PaymentExceedsBalance
from app.domain.money import Money
from app.infrastructure.clock import SystemClock
from app.infrastructure.persistence.sqlalchemy_repositories import (
    SqlAlchemyCashRepository,
    SqlAlchemyReturnRepository,
    SqlAlchemySaleRepository,
    SqlAlchemyStockEntryRepository,
    SqlAlchemySupplierPaymentRepository,
    SqlAlchemyUnitOfWork,
)
from app.services import crud_accounting
from app.utils.api_errors import api_error


def movimientos_de_caja(db: Session, ledger=None) -> AddCashMovement:
    """La salida de caja, armada como la arma `crud_cash`.

    Se construye acá y no se importa hecha porque necesita el mismo `db` de esta
    petición. Lo que importa es que sea **el mismo caso de uso**: así un abono en
    efectivo pasa por las dos comprobaciones del turno —que haya uno abierto y
    que alcance el efectivo— sin que nadie las vuelva a escribir.
    """
    cash = SqlAlchemyCashRepository(db)
    return AddCashMovement(
        cash=cash,
        report=BuildSessionReport(
            sales=SqlAlchemySaleRepository(db),
            returns=SqlAlchemyReturnRepository(db),
            cash=cash,
            clock=SystemClock(),
        ),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
        ledger=ledger,
    )


def pagar(db: Session, entry_id: int, payload, *, user_id: int) -> dict:
    # Un solo libro para el abono y para la salida de caja que lo acompaña: los
    # dos tienen que ver el mismo mapeo, y la salida no deja asiento propio
    # porque lo deja el abono (RN-56).
    contable = crud_accounting.libro(db, user_id=user_id)
    caso = PaySupplier(
        entries=SqlAlchemyStockEntryRepository(db),
        payments=SqlAlchemySupplierPaymentRepository(db),
        movements=movimientos_de_caja(db, contable),
        uow=SqlAlchemyUnitOfWork(db),
        clock=SystemClock(),
        ledger=contable,
    )

    try:
        resultado = caso(
            PaymentRequest(
                entry_id=entry_id,
                amount=Money(payload.amount),
                method=payload.method,
                user_id=user_id,
                reference=payload.reference,
                reason=payload.reason,
            )
        )

    except PurchaseNotFound:
        # 404 y no 403: el filtro por compañía ya hizo que la compra de otra no
        # exista para esta sesión (RNF-1). Una entrada que no es compra también
        # cae acá, y por lo mismo: desde cuentas por pagar no existe.
        raise api_error(404, "entry_not_found") from None
    except PurchaseCancelled:
        raise api_error(400, "purchase_cancelled") from None
    except InvalidPayment as e:
        codigos = {
            "amount_not_positive": "payment_not_positive",
            "invalid_method": "invalid_payment_method",
        }
        raise api_error(400, codigos[e.code], method=payload.method) from None
    except PaymentExceedsBalance as e:
        raise api_error(
            400, "payment_exceeds_balance", balance=e.balance, requested=e.requested
        ) from None
    except NoOpenSession:
        # El mismo código que al mover efectivo: es la misma situación. RN-56 no
        # deja más salida que abrir la caja o pagar por transferencia.
        raise api_error(400, "cash_no_open_session") from None
    except InsufficientCash as e:
        raise api_error(400, "cash_insufficient", available=e.available.as_float()) from None
    except InvalidMovement as e:
        # Solo queda uno alcanzable: el motivo vacío. El tipo lo pone este
        # servicio y el monto ya lo comprobó `check_payment`.
        codigos = {"missing_reason": "cash_missing_reason"}
        raise api_error(400, codigos[e.code]) from None
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise api_error(500, "payment_failed", cause=str(exc))

    return {
        "message": "payment_registered",
        "id_payment": resultado.id_payment,
        "balance": resultado.balance.as_float(),
        "cash_movement_id": resultado.cash_movement_id,
    }
