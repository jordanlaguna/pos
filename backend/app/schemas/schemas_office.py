"""Lo que entra y sale de sucursales y terminales (T-608, RF-26).

**El código entra como texto y no como entero**, aunque sean dígitos: «007» es
lo que va en el comprobante y un entero perdería los ceros por el camino. Quien
escriba `7` igual lo puede mandar —`domain/office.py` lo normaliza— pero el
contrato dice texto, que es lo que de verdad se guarda.

Y **no se puede cambiar** después de creado: no hay `codigo` en los esquemas de
actualización. Cambiarlo movería el número de todos los comprobantes ya emitidos
desde esa sucursal.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BranchIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=10)
    nombre: str = Field(min_length=1, max_length=120)


class BranchUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    activa: bool | None = None


class BranchOut(BaseModel):
    id: int
    codigo: str
    nombre: str
    activa: bool

    model_config = {"from_attributes": True}


class TerminalIn(BaseModel):
    branch_id: int
    codigo: str = Field(min_length=1, max_length=10)
    nombre: str = Field(min_length=1, max_length=120)


class TerminalUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    activa: bool | None = None


class TerminalOut(BaseModel):
    id: int
    branch_id: int
    codigo: str
    nombre: str
    activa: bool

    model_config = {"from_attributes": True}


class OfficeQuota(BaseModel):
    """Cuántas hay y cuántas permite el plan.

    Va en la misma respuesta que las listas para que la pantalla pueda decir «va
    3 de 3» **antes** de abrir el formulario. Enterarse del techo al chocar con
    él, después de llenarlo, es el mismo error de diseño que un botón que
    promete algo que no pasa.
    """

    branches: int
    max_branches: int
    terminals: int
    max_terminals: int


class OfficeOut(BaseModel):
    """Todo de una vez: las sucursales, sus cajas y el cupo.

    Una sola llamada y no tres, por lo mismo que `GET /fe` devuelve los dos
    ambientes: con tres, la pantalla tendría que componer un estado a partir de
    respuestas que pueden llegar de momentos distintos.
    """

    branches: list[BranchOut]
    terminals: list[TerminalOut]
    quota: OfficeQuota
