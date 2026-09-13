"""Proveedores: qué entra y qué sale (F10, RF-41).

Nada de acá lleva frases. Los «no» son código y datos, y la oración la arma el
POS con su catálogo (RN-30).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

#: Los tipos de identificación de Hacienda, los mismos de `companies` (T-621).
#: 01 física, 02 jurídica, 03 DIMEX, 04 NITE.
TIPOS_DE_IDENTIFICACION = ("01", "02", "03", "04")


class SupplierIn(BaseModel):
    """Alta de proveedor.

    `identification` es opcional: a un proveedor informal —el que trae la fruta
    el martes— no se le pide cédula, y obligarla haría que el usuario invente
    una. Sin ella no se le puede reconocer desde un XML, y eso está bien: los
    que facturan electrónicamente sí la traen.
    """

    name: str = Field(min_length=1, max_length=160)
    identification_type: str | None = None
    identification: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=30)
    #: Plazo habitual en días. 0 es contado. Es lo que la ficha de una compra
    #: nueva propone; lo que manda es lo que diga esa compra.
    payment_terms_days: int = Field(default=0, ge=0, le=365)


class SupplierUpdate(SupplierIn):
    """Los mismos campos, más el interruptor de activo.

    Se hereda en vez de repetir: un campo que se agregue arriba y no acá sería
    uno que se puede crear y no corregir.
    """

    is_active: bool = True


class SupplierOut(BaseModel):
    """Un proveedor como lo ve el POS."""

    id: int
    name: str
    identification_type: str | None = None
    identification: str | None = None
    email: str | None = None
    phone: str | None = None
    payment_terms_days: int
    is_active: bool

    model_config = {"from_attributes": True}
