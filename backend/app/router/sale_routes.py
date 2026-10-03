from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.schemas.schemas_sales import SaleDetailResponse, SaleRegister, SaleRegisterSuccess, SalesList
from app.services import crud_sale
from app.utils.api_errors import api_error
from app.utils.auth_dependency import Sesion, get_current_user

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
    current: Sesion = Depends(get_current_user),
):
    # Este endpoint solo transporta (T-110). Las reglas se fueron al caso de
    # uso, y con motivo:
    #
    # - **El número de factura único** es una regla de la venta, no del
    #   transporte: dos ventas con el mismo consecutivo son un problema de
    #   Hacienda, no de HTTP.
    # - **El efectivo y el vuelto** se comprobaban contra el total que mandaba
    #   el POS, que es justo el número del que ya no se fía nadie. Ahora se
    #   miden contra el total que calcula el servidor, y el vuelto ni se
    #   recibe: se calcula.
    return crud_sale.create_sale(db=db, sale=sale)


@router.get("/sales_list", response_model=list[SalesList])
def get_all_sales(
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    return crud_sale.get_all_sales(db=db)


@router.get("/sale/{sale_id}", response_model=SaleDetailResponse)
def get_sale_detail(
    sale_id: int,
    db: Session = Depends(get_db),
    current: Sesion = Depends(get_current_user),
):
    """Venta con sus líneas de detalle.

    Sin este endpoint la factura no puede mostrar qué se vendió y las
    devoluciones no tienen sobre qué trabajar.
    """
    detail = crud_sale.get_sale_detail(db, sale_id)
    if not detail:
        raise api_error(404, "sale_not_found")
    return detail


# `GET /sales/pdf/{id}` se quitó (T-922, RN-86). Dibujaba con reportlab un
# cuarto documento sin emisor, sin desglose por tarifa, sin el idioma del
# documento y con sus rótulos escritos en español —contra RN-30—, y no llevaba
# nada de lo que Hacienda pide imprimir. Para que dijera lo mismo que las
# plantillas habría que haberlas escrito dos veces. El PDF sale de imprimir la
# plantilla del POS, que se arma cada vez y no se guarda (RN-82).
