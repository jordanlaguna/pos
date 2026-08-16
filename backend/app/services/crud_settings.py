"""Configuración del negocio: moneda, impuesto, documentos, marca.

Es una sola fila. Si no existe, se crea vacía en la primera lectura, de modo que
un sistema recién instalado no necesita ningún paso previo: el frontend aplica
sus valores por omisión sobre un objeto vacío y el POS arranca funcionando.
"""

import json
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.model_settings import Settings

SETTINGS_ID = 1

# Tope de la configuración serializada. No es una restricción de la base (el
# campo es TEXT, 64 KB), es un cortafuegos: la configuración son unas decenas de
# campos y cualquier cosa más grande significa que algo se está usando mal.
MAX_DATA_BYTES = 20_000

# El impuesto por omisión mientras nadie lo configure. Es el IVA de Costa Rica,
# el mismo que traía fijo el WinForms.
DEFAULT_TAX_RATE = Decimal("0.13")


def _row(db: Session) -> Settings:
    row = db.query(Settings).filter(Settings.id == SETTINGS_ID).first()
    if row is None:
        row = Settings(id=SETTINGS_ID, data="{}")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _parse(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        # Fila corrupta: se devuelve vacía y el frontend aplica sus valores por
        # omisión. Vale más un POS con la moneda de fábrica que uno que no abre.
        return {}
    return value if isinstance(value, dict) else {}


def get_settings(db: Session) -> dict:
    row = _row(db)
    logo = None
    if row.logo_data and row.logo_mime:
        logo = {"mime": row.logo_mime, "data": row.logo_data}

    return {
        "data": _parse(row.data),
        "logo": logo,
        "updated_at": row.updated_at,
        "updated_by": row.updated_by,
    }


def save_settings(
    db: Session,
    data: dict,
    logo: dict | None,
    keep_logo: bool,
    user_id: int,
) -> dict:
    serialized = json.dumps(data, ensure_ascii=False)
    if len(serialized.encode("utf-8")) > MAX_DATA_BYTES:
        raise HTTPException(
            status_code=400,
            detail="La configuración es demasiado grande.",
        )

    # Único campo que este backend lee por su cuenta (crud_return lo usa para
    # calcular el reembolso), así que es el único que valida aquí.
    tax = data.get("impuesto", {})
    if isinstance(tax, dict) and "tasa" in tax:
        try:
            rate = Decimal(str(tax["tasa"]))
        except Exception:
            raise HTTPException(status_code=400, detail="La tasa de impuesto no es un número.")
        if rate < 0 or rate > 1:
            raise HTTPException(
                status_code=400,
                detail="La tasa de impuesto se expresa entre 0 y 1 (0.13 = 13 %).",
            )

    row = _row(db)
    try:
        row.data = serialized
        if logo is not None:
            row.logo_mime = logo["mime"]
            row.logo_data = logo["data"]
        elif not keep_logo:
            row.logo_mime = None
            row.logo_data = None
        row.updated_at = datetime.now()
        row.updated_by = user_id
        db.commit()
        db.refresh(row)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"No se pudo guardar la configuración: {exc}")

    return get_settings(db)


def get_tax_rate(db: Session) -> Decimal:
    """Tasa de impuesto configurada, para quien la necesite del lado del servidor.

    Devuelve la de Costa Rica mientras nadie configure otra. Cualquier valor
    fuera de rango se ignora en vez de propagarse a un cálculo de plata.
    """
    try:
        value = _parse(_row(db).data).get("impuesto", {}).get("tasa")
        if value is None:
            return DEFAULT_TAX_RATE
        rate = Decimal(str(value))
        return rate if 0 <= rate <= 1 else DEFAULT_TAX_RATE
    except Exception:
        return DEFAULT_TAX_RATE
