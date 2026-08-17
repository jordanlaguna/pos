from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.model_user import User
from app.schemas.schemas_report import (
    LowStockProduct,
    PaymentBreakdown,
    ReportSummary,
    SalesByDay,
    TopProduct,
)
from app.services import crud_report
from app.utils.auth_dependency import Sesion, require_admin

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# `from` es palabra reservada en Python, así que el parámetro se llama date_from
# y el alias lo expone como `?from=` en la URL, que es lo que manda el frontend.
FromParam = Query(None, alias="from", description="Fecha inicial YYYY-MM-DD")
ToParam = Query(None, alias="to", description="Fecha final YYYY-MM-DD")


# Los reportes exponen la facturación completa del negocio: solo administradores.
@router.get("/summary", response_model=ReportSummary)
def get_summary(
    date_from: str | None = FromParam,
    date_to: str | None = ToParam,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    return crud_report.summary(db, date_from, date_to)


@router.get("/top_products", response_model=list[TopProduct])
def get_top_products(
    date_from: str | None = FromParam,
    date_to: str | None = ToParam,
    limit: int = 8,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    return crud_report.top_products(db, date_from, date_to, limit)


@router.get("/sales_by_day", response_model=list[SalesByDay])
def get_sales_by_day(
    date_from: str | None = FromParam,
    date_to: str | None = ToParam,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    return crud_report.sales_by_day(db, date_from, date_to)


@router.get("/by_payment_method", response_model=list[PaymentBreakdown])
def get_by_payment_method(
    date_from: str | None = FromParam,
    date_to: str | None = ToParam,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    return crud_report.by_payment_method(db, date_from, date_to)


@router.get("/low_stock", response_model=list[LowStockProduct])
def get_low_stock(
    threshold: int = 10,
    db: Session = Depends(get_db),
    admin: Sesion = Depends(require_admin),
):
    return crud_report.low_stock(db, threshold)
