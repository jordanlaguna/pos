"""Configuración del negocio: moneda, impuesto, documentos, marca.

Una fila por compañía. Si no existe, se crea vacía en la primera lectura, de
modo que una compañía recién dada de alta no necesita ningún paso previo: el
frontend aplica sus valores por omisión sobre un objeto vacío y el POS arranca
funcionando.
"""

import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.model_settings import Settings
from app.utils import clock
from app.utils.tenancy import compania_actual

# Tope de la configuración serializada. No es una restricción de la base (el
# campo es TEXT, 64 KB), es un cortafuegos: la configuración son unas decenas de
# campos y cualquier cosa más grande significa que algo se está usando mal.
MAX_DATA_BYTES = 20_000

# El impuesto por omisión mientras nadie lo configure. Es el IVA de Costa Rica,
# el mismo que traía fijo el WinForms.
DEFAULT_TAX_RATE = Decimal("0.13")


def _row(db: Session) -> Settings:
    """La fila de ESTA compañía.

    Antes era `WHERE id = 1`, y con una sola compañía eso era exacto. Ahora el
    `WHERE company_id` lo pone el filtro automático, así que la consulta no
    lleva condición: pedir «la configuración» ya significa «la de la compañía
    de esta petición».
    """
    row = db.query(Settings).first()
    if row is None:
        row = Settings(company_id=compania_actual(), data="{}")
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
        row.updated_at = clock.now()
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
        data = _parse(_row(db).data)
        # Las dos formas de la clave: `tax.rate` desde T-113 y el
        # `impuesto.tasa` de antes. Una fila guardada con la versión anterior
        # tiene que seguir entendiéndose; si no, actualizar el sistema haría que
        # el POS cobrara con la tasa de fábrica sin decir nada.
        value = data.get("tax", {}).get("rate")
        if value is None:
            value = data.get("impuesto", {}).get("tasa")
        if value is None:
            return DEFAULT_TAX_RATE
        rate = Decimal(str(value))
        return rate if 0 <= rate <= 1 else DEFAULT_TAX_RATE
    except Exception:
        return DEFAULT_TAX_RATE
