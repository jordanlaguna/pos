"""
El catálogo CABYS, proxeado (T-502, T-503).

**Proxy y no llamada desde el navegador**, por tres razones que están en el plan
§6.2 y que siguen siendo ciertas: el POS puede estar en una LAN sin salida, no se
quiere exponer internet al cliente ni pelear con CORS, y así la respuesta se
cachea **una vez para todas las compañías** en vez de una por caja.

Las rutas son de lectura y las puede usar cualquier sesión: clasificar un
producto es de administrador, pero *buscar* un código no cambia nada y el cajero
que ve una tarifa rara necesita poder mirarlo.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.application.use_cases.search_cabys import CabysAnswer, SearchCabys
from app.database.database import SessionLocal
from app.domain.cabys import InvalidCabysCode
from app.infrastructure.clock import SystemClock
from app.infrastructure.external.hacienda_cabys import HaciendaCabysCatalog
from app.infrastructure.persistence.sqlalchemy_repositories import (
    SqlAlchemyCabysCacheRepository,
)
from app.schemas.schemas_cabys import CabysItem, CabysSearchResponse
from app.utils.api_errors import api_error
from app.utils.auth_dependency import Sesion, get_current_user

router = APIRouter()


def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _caso(db: Session) -> SearchCabys:
    return SearchCabys(
        catalog=HaciendaCabysCatalog(),
        cache=SqlAlchemyCabysCacheRepository(db),
        clock=SystemClock(),
    )


def _respuesta(answer: CabysAnswer) -> CabysSearchResponse:
    return CabysSearchResponse(
        source=answer.source,
        cached_at=answer.cached_at,
        items=[
            CabysItem(
                code=e.code,
                description=e.description,
                # Al POS le viaja la tarifa entre 0 y 1, como todo el sistema.
                # Hacienda la publica en porcentaje y eso se traduce en el
                # adaptador: acá adentro ya no circula un 13.
                tax_rate=float(e.tax_rate.value),
            )
            for e in answer.entries
        ],
    )


@router.get("/buscar", response_model=CabysSearchResponse)
def buscar(
    q: str = Query("", description="Texto a buscar en la descripción"),
    top: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db_session),
    current: Sesion = Depends(get_current_user),
):
    """Busca por texto.

    **Nunca falla por falta de internet** (RNF-4): si Hacienda no contesta,
    responde desde la caché y lo dice en `source`. Quien decide si eso le sirve
    es la persona que está clasificando, no el programa.
    """
    return _respuesta(_caso(db).by_text(q, top))


@router.get("/{codigo}", response_model=CabysSearchResponse)
def por_codigo(
    codigo: str,
    db: Session = Depends(get_db_session),
    current: Sesion = Depends(get_current_user),
):
    """Un código exacto.

    Los dos «no» de acá son distintos y por eso son dos códigos: el formato malo
    es un error de quien pide, y «Hacienda dice que no existe» es una respuesta
    del catálogo. Que no haya internet no es ninguno de los dos: eso devuelve 200
    con `source: cache`.
    """
    try:
        answer = _caso(db).by_code(codigo)
    except InvalidCabysCode as e:
        raise api_error(400, "cabys_invalid_code", value=str(e.value), reason=e.code) from None

    if not answer.entries and answer.source == "hacienda":
        raise api_error(404, "cabys_not_found", code=codigo)
    return _respuesta(answer)
