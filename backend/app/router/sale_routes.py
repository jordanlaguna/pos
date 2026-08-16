import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.models.model_product import Product
from app.models.model_sale_details import SaleDetail
from app.models.model_sales import Sale
from app.models.model_user import User
from app.schemas.schemas_sales import SaleDetailResponse, SaleRegister, SaleRegisterSuccess, SalesList
from app.services import crud_sale
from app.utils.auth_dependency import get_current_user

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/add_sale", response_model=SaleRegisterSuccess)
def register_sale(
    sale: SaleRegister,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    existing = db.query(Sale).filter(Sale.sale_number == sale.sale_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe una venta con este número de venta.")
    if sale.cash_received < sale.total:
        raise HTTPException(
            status_code=400,
            detail="El efectivo recibido no puede ser menor al total de la venta.",
        )
    if sale.change_given < 0:
        raise HTTPException(status_code=400, detail="El cambio dado no puede ser negativo.")

    return crud_sale.create_sale(db=db, sale=sale)


@router.get("/sales_list", response_model=list[SalesList])
def get_all_sales(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    return crud_sale.get_all_sales(db=db)


@router.get("/sale/{sale_id}", response_model=SaleDetailResponse)
def get_sale_detail(
    sale_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Venta con sus líneas de detalle.

    Sin este endpoint la factura no puede mostrar qué se vendió y las
    devoluciones no tienen sobre qué trabajar.
    """
    detail = crud_sale.get_sale_detail(db, sale_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    return detail


@router.get("/pdf/{sale_id}", response_class=FileResponse)
def generate_invoice_pdf(
    sale_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    details = db.query(SaleDetail).filter(SaleDetail.sale_id == sale.id).all()
    if not details:
        raise HTTPException(status_code=404, detail="Detalles de la venta no encontrados")

    temp_dir = Path(os.getenv("TEMP") or tempfile.gettempdir())
    file_path = temp_dir / f"venta_{sale.sale_number}.pdf"

    c = canvas.Canvas(str(file_path), pagesize=letter)
    width, height = letter
    y = height - 50

    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, f"Factura: {sale.sale_number}")
    y -= 30

    c.setFont("Helvetica", 12)
    c.drawString(50, y, f"Fecha: {sale.created_at.strftime('%d/%m/%Y %H:%M')}")
    y -= 20
    c.drawString(50, y, f"Metodo de pago: {sale.payment_method}")
    y -= 30

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Detalle:")
    y -= 20

    c.setFont("Helvetica", 11)
    for detail in details:
        product = db.query(Product).filter(Product.id_product == detail.product_id).first()
        name = product.name if product else f"Producto #{detail.product_id}"
        c.drawString(
            50,
            y,
            f"{name} x{detail.quantity}  -  Unit: {detail.unit_price:,.2f}  -  Subtotal: {detail.subtotal:,.2f}",
        )
        y -= 18
        if y < 120:
            c.showPage()
            c.setFont("Helvetica", 11)
            y = height - 50

    y -= 12
    c.setFont("Helvetica", 12)
    c.drawString(50, y, f"Subtotal: {sale.subtotal:,.2f}")
    y -= 18
    c.drawString(50, y, f"IVA: {sale.tax:,.2f}")
    y -= 18
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, y, f"Total: {sale.total:,.2f}")

    c.save()

    return FileResponse(path=file_path, filename=file_path.name, media_type="application/pdf")
