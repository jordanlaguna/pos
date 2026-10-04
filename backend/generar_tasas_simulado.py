#!/usr/bin/env python3
"""Escribe las tasas de planilla para el modo simulado del POS (T-1204).

    python generar_tasas_simulado.py

El simulado tiene que responder lo mismo que la API (CLAUDE.md), y la API siembra
`app/infrastructure/payroll_rates_cr.py`. Copiar las cifras a mano en TypeScript
sería tener dos fuentes para la misma verdad; esto genera
`frontend/src/lib/server/mock/payrollRates.ts` desde el archivo de Python, y
`tests/test_siembra_planilla.py` falla si el generado quedó viejo.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from app.domain.payroll import REQUIRED_CONTRIBUTIONS
from app.infrastructure import payroll_rates_cr as cr

DESTINO = Path(__file__).resolve().parent.parent / "frontend/src/lib/server/mock/payrollRates.ts"


def _n(valor: Decimal | None) -> float | None:
    return None if valor is None else float(valor)


def contenido() -> str:
    datos = {
        "country": cr.COUNTRY,
        "verified_at": cr.VERIFIED_AT.isoformat(),
        "required": sorted(f"{c}:{p}" for c, p in REQUIRED_CONTRIBUTIONS[cr.COUNTRY]),
        "rates": [
            {
                "concept": r.concept,
                "payer": r.payer,
                "value": _n(r.value),
                "valid_from": r.valid_from.isoformat(),
                "source": r.source,
            }
            for r in cr.RATES
        ],
        "brackets": [
            {
                "lower": _n(d),
                "upper": _n(h),
                "rate": _n(t),
                "valid_from": cr.DESDE_2026.isoformat(),
                "source": cr.BRACKETS_SOURCE,
            }
            for d, h, t in cr.BRACKETS
        ],
        "credits": [
            {"concept": c, "amount": _n(m), "valid_from": cr.DESDE_2026.isoformat(), "source": cr.BRACKETS_SOURCE}
            for c, m in cr.CREDITS.items()
        ],
        "severance": [
            {"years_from": _n(d), "years_to": _n(h), "days": _n(dias), "source": cr.SEVERANCE_SOURCE}
            for d, h, dias in cr.SEVERANCE
        ],
        "severance_valid_from": cr.SEVERANCE_VALID_FROM.isoformat(),
    }
    cuerpo = json.dumps(datos, ensure_ascii=False, indent="\t")
    return (
        "/**\n"
        " * Las tasas de planilla que siembra la API (T-1204), para el modo simulado.\n"
        " *\n"
        " * **Generado**: no se edita a mano. Sale de\n"
        " * `backend/app/infrastructure/payroll_rates_cr.py` con\n"
        " * `python backend/generar_tasas_simulado.py`, y `test_siembra_planilla.py`\n"
        " * falla si este archivo y aquel dejan de decir lo mismo.\n"
        " */\n\n"
        f"export const PAYROLL_SEED = {cuerpo} as const;\n"
    )


if __name__ == "__main__":
    DESTINO.write_text(contenido(), encoding="utf-8", newline="\n")
    print(f"Escrito {DESTINO}")
