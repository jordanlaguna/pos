"""Las tasas de planilla: sembrarlas, leerlas a una fecha y agregar una (T-1204).

Las cuatro tablas son **del país**, no de una compañía (RN-67): no heredan el
filtro de `tenancy.py` y se leen igual desde una sesión de compañía que desde
el panel de soporte. No hay dato de nadie; son normas publicadas, con su fuente.

Una tasa no se edita nunca. La que cambia entra como fila nueva con su
`valid_from`, y el dominio decide cuál rige a cada fecha (`rates_at`). Lo que
esto protege es la corrida ya calculada: su boleta sale de sus rubros
congelados (RN-66), pero un borrador recalculado tiene que ver la tasa que regía
en su corte, no la de hoy.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain.errors import InvalidPayrollRate, InvalidTaxBrackets, RateNotNewer
from app.domain.payroll import REQUIRED_CONTRIBUTIONS, check_new_rate, check_tax_brackets, is_stale
from app.infrastructure import payroll_rates_cr as cr
from app.models.model_payroll import IncomeTaxBracket, IncomeTaxCredit, PayrollRate, SeveranceBracket
from app.utils.api_errors import api_error


def _rige(fila, on: date) -> bool:
    # La cesantía no tiene `valid_to`: una ley la reemplaza entera con otra
    # `valid_from`, y el juego más reciente gana.
    hasta = getattr(fila, "valid_to", None)
    return fila.valid_from <= on and (hasta is None or on <= hasta)


def _vigentes(filas, on: date, clave) -> list:
    """De cada clave, la fila de `valid_from` más reciente que rige el día `on`."""
    elegidas: dict = {}
    for fila in filas:
        if not _rige(fila, on):
            continue
        k = clave(fila)
        if k not in elegidas or fila.valid_from > elegidas[k].valid_from:
            elegidas[k] = fila
    return [elegidas[k] for k in sorted(elegidas)]


def _ultimo_juego(filas, on: date) -> list:
    """Los tramos o la tabla del juego más reciente que rige: todos los de la
    misma `valid_from`. Un decreto nuevo trae el juego entero, no un tramo."""
    fechas = [f.valid_from for f in filas if _rige(f, on)]
    if not fechas:
        return []
    ultima = max(fechas)
    return [f for f in filas if f.valid_from == ultima]


def vigentes(db: Session, on: date, today: date, country: str = cr.COUNTRY) -> dict:
    """Lo que rige a una fecha, con su fuente, y lo que falta o está viejo."""
    tasas = _vigentes(
        db.query(PayrollRate).filter(PayrollRate.country == country).all(),
        on,
        lambda f: (f.payer, f.concept),
    )
    tramos = sorted(
        _ultimo_juego(db.query(IncomeTaxBracket).filter(IncomeTaxBracket.country == country).all(), on),
        key=lambda f: f.lower_bound,
    )
    creditos = _vigentes(
        db.query(IncomeTaxCredit).filter(IncomeTaxCredit.country == country).all(),
        on,
        lambda f: f.concept,
    )
    cesantia = sorted(
        _ultimo_juego(db.query(SeveranceBracket).filter(SeveranceBracket.country == country).all(), on),
        key=lambda f: f.years_from,
    )
    presentes = {(t.concept, t.payer) for t in tasas}
    faltan = sorted(f"{c}:{p}" for c, p in REQUIRED_CONTRIBUTIONS.get(country, frozenset()) - presentes)

    salida_tasas = [
        {
            "concept": t.concept,
            "payer": t.payer,
            "value": t.value,
            "valid_from": t.valid_from,
            "valid_to": t.valid_to,
            "source": t.source,
            "verified_at": t.verified_at,
            "stale": is_stale(t.verified_at, today),
        }
        for t in tasas
    ]
    return {
        "on": on,
        "country": country,
        "rates": salida_tasas,
        "brackets": [
            {
                "lower": t.lower_bound,
                "upper": t.upper_bound,
                "rate": t.rate,
                "valid_from": t.valid_from,
                "source": t.source,
                "verified_at": t.verified_at,
            }
            for t in tramos
        ],
        "credits": [
            {"concept": c.concept, "amount": c.amount, "valid_from": c.valid_from, "source": c.source}
            for c in creditos
        ],
        "severance": [
            {"years_from": s.years_from, "years_to": s.years_to, "days": s.days, "source": s.source}
            for s in cesantia
        ],
        "missing": faltan,
        "stale": any(t["stale"] for t in salida_tasas) or any(is_stale(t.verified_at, today) for t in tramos),
    }


def agregar(
    db: Session,
    *,
    concept: str,
    payer: str,
    value: Decimal,
    valid_from: date,
    source: str,
    today: date,
    country: str = cr.COUNTRY,
) -> PayrollRate:
    """Agrega una tasa con su vigencia. No hace commit: lo hace quien llama.

    `verified_at` es hoy: quien la carga es quien la acaba de comprobar.
    """
    ultima = (
        db.query(func.max(PayrollRate.valid_from))
        .filter(PayrollRate.country == country, PayrollRate.concept == concept, PayrollRate.payer == payer)
        .scalar()
    )
    try:
        check_new_rate(concept, payer, value, valid_from, ultima)
    except InvalidPayrollRate as e:
        raise api_error(400, "invalid_payroll_rate", field=e.field, reason=e.reason) from None
    except RateNotNewer as e:
        raise api_error(
            409, "payroll_rate_not_newer", concept=e.concept, payer=e.payer, latest=e.latest.isoformat()
        ) from None
    fila = PayrollRate(
        country=country,
        concept=concept,
        payer=payer,
        value=value,
        valid_from=valid_from,
        source=source,
        verified_at=today,
    )
    db.add(fila)
    db.flush()
    return fila


def sembrar(db: Session) -> dict[str, int]:
    """Inserta lo de `payroll_rates_cr.py` que todavía no esté. No hace commit.

    Repetible: una fila que ya existe con la misma clave no se toca, ni siquiera
    si su cifra difiere —eso sería editar una tasa—. Devuelve cuántas entraron de
    cada tabla.
    """
    nuevas = {"rates": 0, "brackets": 0, "credits": 0, "severance": 0}

    for r in cr.RATES:
        existe = (
            db.query(PayrollRate.id)
            .filter_by(country=cr.COUNTRY, concept=r.concept, payer=r.payer, valid_from=r.valid_from)
            .first()
        )
        if existe is None:
            db.add(
                PayrollRate(
                    country=cr.COUNTRY,
                    concept=r.concept,
                    payer=r.payer,
                    value=r.value,
                    valid_from=r.valid_from,
                    source=r.source,
                    verified_at=cr.VERIFIED_AT,
                )
            )
            nuevas["rates"] += 1

    for desde, hasta, tasa in cr.BRACKETS:
        existe = (
            db.query(IncomeTaxBracket.id)
            .filter_by(country=cr.COUNTRY, valid_from=cr.DESDE_2026, lower_bound=desde)
            .first()
        )
        if existe is None:
            db.add(
                IncomeTaxBracket(
                    country=cr.COUNTRY,
                    valid_from=cr.DESDE_2026,
                    lower_bound=desde,
                    upper_bound=hasta,
                    rate=tasa,
                    source=cr.BRACKETS_SOURCE,
                    verified_at=cr.VERIFIED_AT,
                )
            )
            nuevas["brackets"] += 1

    for concepto, monto in cr.CREDITS.items():
        existe = (
            db.query(IncomeTaxCredit.id)
            .filter_by(country=cr.COUNTRY, concept=concepto, valid_from=cr.DESDE_2026)
            .first()
        )
        if existe is None:
            db.add(
                IncomeTaxCredit(
                    country=cr.COUNTRY,
                    concept=concepto,
                    valid_from=cr.DESDE_2026,
                    amount=monto,
                    source=cr.BRACKETS_SOURCE,
                    verified_at=cr.VERIFIED_AT,
                )
            )
            nuevas["credits"] += 1

    for desde, hasta, dias in cr.SEVERANCE:
        existe = (
            db.query(SeveranceBracket.id)
            .filter_by(country=cr.COUNTRY, valid_from=cr.SEVERANCE_VALID_FROM, years_from=desde)
            .first()
        )
        if existe is None:
            db.add(
                SeveranceBracket(
                    country=cr.COUNTRY,
                    valid_from=cr.SEVERANCE_VALID_FROM,
                    years_from=desde,
                    years_to=hasta,
                    days=dias,
                    source=cr.SEVERANCE_SOURCE,
                )
            )
            nuevas["severance"] += 1

    db.flush()
    return nuevas


def agregar_tramos(
    db: Session,
    *,
    valid_from: date,
    brackets: list[tuple[Decimal, Decimal | None, Decimal]],
    credits: dict[str, Decimal],
    source: str,
    today: date,
    country: str = cr.COUNTRY,
) -> dict:
    """El juego de tramos y créditos del año siguiente (T-1221, RN-73). No hace commit.

    Entra el juego entero con una sola vigencia, nunca un tramo suelto: el
    decreto los publica juntos y `GET /payroll/rates?on=` devuelve el juego más
    reciente que rige, así que medio juego nuevo taparía la mitad del viejo.
    """
    ultima = (
        db.query(func.max(IncomeTaxBracket.valid_from)).filter(IncomeTaxBracket.country == country).scalar()
    )
    try:
        check_tax_brackets(brackets, credits, valid_from, ultima)
    except InvalidTaxBrackets as e:
        raise api_error(400, "invalid_tax_brackets", reason=e.reason, index=e.index) from None
    except RateNotNewer as e:
        raise api_error(
            409, "payroll_rate_not_newer", concept=e.concept, payer=e.payer, latest=e.latest.isoformat()
        ) from None

    for desde, hasta, tasa in brackets:
        db.add(
            IncomeTaxBracket(
                country=country,
                valid_from=valid_from,
                lower_bound=desde,
                upper_bound=hasta,
                rate=tasa,
                source=source,
                verified_at=today,
            )
        )
    for concepto, monto in credits.items():
        db.add(
            IncomeTaxCredit(
                country=country,
                concept=concepto,
                valid_from=valid_from,
                amount=monto,
                source=source,
                verified_at=today,
            )
        )
    db.flush()
    vigente = vigentes(db, valid_from, today, country)
    return {"valid_from": valid_from, "brackets": vigente["brackets"], "credits": vigente["credits"]}
