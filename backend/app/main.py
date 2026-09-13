import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.database import Base, engine

# Los modelos se importan antes de create_all para que SQLAlchemy conozca todas
# las tablas, incluidas las nuevas de caja y devoluciones.
from app.models.model_accounting import (  # noqa: F401
    Account,
    AccountingPeriod,
    AccountMapping,
    JournalEntry,
    JournalLine,
)
from app.models.model_cash import CashMovement, CashSession  # noqa: F401
from app.models.model_company import (  # noqa: F401
    AuditLog,
    Branch,
    Company,
    Plan,
    Terminal,
    UserCompany,
)
from app.models.model_cabys import CabysCache  # noqa: F401
from app.models.model_categories import Category  # noqa: F401
from app.models.model_client import Client  # noqa: F401
from app.models.model_fe import FeCredentials, FeSequence  # noqa: F401
from app.models.model_person import Person  # noqa: F401
from app.models.model_product import Product  # noqa: F401
from app.models.model_return import Return, ReturnDetail  # noqa: F401
from app.models.model_sale_details import SaleDetail  # noqa: F401
from app.models.model_sales import Sale  # noqa: F401
from app.models.model_settings import Settings  # noqa: F401
from app.models.model_stock_entry import StockEntry, StockEntryDetail  # noqa: F401
from app.models.model_supplier import Supplier, SupplierPayment  # noqa: F401
from app.models.model_user import User  # noqa: F401
from app.router import (
    accounting_routes,
    auth_routes,
    cabys_routes,
    cash_routes,
    categories_routes,
    client_routes,
    payable_routes,
    person_routes,
    product_routes,
    purchase_routes,
    report_routes,
    return_routes,
    sale_routes,
    settings_routes,
    stock_entry_routes,
    supplier_routes,
    support_routes,
    user_routes,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Postsys API", version="2.0.0")

# ---------------------------------------------------------------------------
# CORS
#
# El frontend SvelteKit habla con este backend desde su propio servidor, así que
# en la práctica no hay petición del navegador que cruce origen. Se deja
# configurado por si alguna vez se consume la API directo desde el navegador.
# ALLOWED_ORIGINS es una lista separada por comas; vacío = sin CORS habilitado.
# ---------------------------------------------------------------------------
origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth_routes.router, prefix="/auth", tags=["Auth"])
app.include_router(user_routes.router, prefix="/users", tags=["Users"])
app.include_router(person_routes.router, prefix="/persons", tags=["Persons"])
app.include_router(client_routes.router, prefix="/clients", tags=["Clients"])
app.include_router(product_routes.router, prefix="/products", tags=["Products"])
app.include_router(sale_routes.router, prefix="/sales", tags=["Sales"])
app.include_router(categories_routes.router, prefix="/categories", tags=["Categories"])
# El catálogo CABYS va proxeado y no se llama desde el navegador: el POS puede
# estar en una LAN sin salida, y así la respuesta se cachea una vez para todas
# las compañías (plan §6.2).
app.include_router(cabys_routes.router, prefix="/cabys", tags=["CABYS"])
app.include_router(cash_routes.router, prefix="/cash", tags=["Cash register"])
app.include_router(return_routes.router, prefix="/returns", tags=["Returns"])
app.include_router(report_routes.router, prefix="/reports", tags=["Reports"])
app.include_router(
    stock_entry_routes.router, prefix="/inventory", tags=["Inventory entries"]
)
app.include_router(supplier_routes.router, prefix="/suppliers", tags=["Suppliers"])
app.include_router(purchase_routes.router, prefix="/purchases", tags=["Purchases"])
app.include_router(payable_routes.router, prefix="/payables", tags=["Payables"])
app.include_router(accounting_routes.router, prefix="/accounting", tags=["Accounting"])
app.include_router(settings_routes.router, prefix="/settings", tags=["Settings"])
# El panel de soporte va bajo /support y no bajo /admin: `admin` ya es el rol del
# administrador de una compañía, y dos cosas distintas con el mismo nombre en el
# mismo API se confunden. En el POS las pantallas sí son /admin, que es el nombre
# que pide T-302 y el que se lee bien en una barra de direcciones.
app.include_router(support_routes.router, prefix="/support", tags=["Support"])


@app.get("/")
def root():
    return {"message": "API de postsys activa 🚀", "version": "2.0.0"}


@app.get("/health")
def health():
    """Sonda de salud: el frontend la usa para saber si la VM está en línea."""
    return {"status": "ok"}
