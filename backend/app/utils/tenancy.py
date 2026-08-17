"""Aislamiento entre compañías (T-206, plan §3.3).

Una sola base guarda los datos de todos los clientes del producto. Lo que impide
que el POS de un negocio muestre las ventas de otro no es acordarse de escribir
`WHERE company_id = ?` en cada consulta: es esto.

La compañía viaja en un `ContextVar` —uno por petición, porque `ContextVar` es
local a la tarea de asyncio— y un escuchador de SQLAlchemy la inyecta en toda
consulta del ORM que toque una tabla de negocio.

**Falla cerrado.** Si una consulta toca una tabla de negocio y no hay compañía,
lanza `SinCompania` en vez de devolver las filas de todo el mundo. La primera
versión de este filtro decía «si hay compañía, filtrá», y con un usuario por
compañía nunca se notaba porque el `company_id` siempre venía en el token. La
pantalla de selección (RF-27) crea justo el estado que faltaba —autenticado y
todavía sin compañía— y en esa ventana una consulta permisiva devuelve las filas
de TODAS las compañías: sin error, sin aviso, en un reporte que se ve perfecto.

Límite conocido: `with_loader_criteria` cubre los SELECT del ORM. **No** cubre el
SQL agregado de `crud_report.py` ni los UPDATE/DELETE masivos. Esos llevan el
filtro escrito a mano y su propia prueba (T-209).
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from sqlalchemy import Column, ForeignKey, Integer, event
from sqlalchemy.orm import Session, declared_attr, with_loader_criteria

#: La compañía de la petición en curso. `None` significa «todavía no se sabe»,
#: que es distinto de «todas»: ver `SinCompania`.
current_company: ContextVar[int | None] = ContextVar("current_company", default=None)

#: Dónde y en qué caja está ocurriendo lo que se registra (RN-14). Salen del
#: token igual que la compañía, nunca de lo que manda el cliente: una venta no
#: puede decir en qué terminal se cobró, porque entonces podría mentir y el
#: arqueo de otra caja saldría cuadrado con plata que no pasó por ahí.
current_branch: ContextVar[int | None] = ContextVar("current_branch", default=None)
current_terminal: ContextVar[int | None] = ContextVar("current_terminal", default=None)

#: Nombre de la opción de ejecución que desactiva el filtro. Se escribe así, en
#: español y largo, para que salte a la vista al leer el código: cada aparición
#: es una consulta que cruza compañías a propósito.
SIN_FILTRO = "sin_filtro_de_compania"


class SinCompania(Exception):
    """Se intentó leer una tabla de negocio sin compañía en la petición.

    No es un error del usuario sino del programa: significa que una ruta llegó
    a la base sin pasar por la dependencia que fija la compañía, o que una
    consulta que cruza compañías a propósito olvidó pedirlo con `sin_filtro`.
    """


class TenantMixin:
    """Lo heredan las tablas de negocio, y solo ellas.

    `users` y `persons` quedan fuera: son identidad, no negocio. Una persona
    tiene una cuenta y puede tener membresía en varias compañías (RN-3), así que
    preguntar «a qué compañía pertenece este usuario» no tiene respuesta.
    """

    # `declared_attr` y no un `Column` suelto: un `ForeignKey` no se puede
    # compartir entre clases, y con el mixin plano las doce tablas terminarían
    # apuntando al mismo objeto.
    #
    # Sin anotación de retorno a propósito: con `-> Column`, SQLAlchemy 2.0 cree
    # que se está usando la forma declarativa con anotaciones y exige
    # `Mapped[...]`. La firma se queda desnuda y el tipo lo dice el `Column`.
    @declared_attr
    def company_id(cls):  # noqa: N805
        return Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)


@contextmanager
def compania(
    cid: int | None, *, sucursal: int | None = None, terminal: int | None = None
) -> Iterator[None]:
    """Fija compañía —y opcionalmente sucursal y terminal— mientras dure el bloque.

    Lo usan la dependencia de FastAPI, `seed.py` y las pruebas. Restaura los
    valores anteriores al salir, incluso si el bloque lanza, porque en las
    pruebas un `ContextVar` que queda sucio hace fallar la prueba siguiente y no
    la que tiene el defecto.
    """
    tokens = (
        current_company.set(cid),
        current_branch.set(sucursal),
        current_terminal.set(terminal),
    )
    try:
        yield
    finally:
        current_terminal.reset(tokens[2])
        current_branch.reset(tokens[1])
        current_company.reset(tokens[0])


def compania_actual() -> int:
    """La compañía de la petición, o `SinCompania` si no hay.

    Para el poco código que necesita el número en la mano —crear la fila de
    configuración de una compañía nueva, por ejemplo— en vez de que se lo
    apliquen por debajo.
    """
    cid = current_company.get()
    if cid is None:
        raise SinCompania("Se pidió la compañía actual y no hay ninguna en el contexto.")
    return cid


def sucursal_actual() -> int:
    """La sucursal de la petición. Falla cerrado, igual que la compañía."""
    bid = current_branch.get()
    if bid is None:
        raise SinCompania("Se pidió la sucursal actual y no hay ninguna en el contexto.")
    return bid


def terminal_actual() -> int:
    """La terminal de la petición. Falla cerrado, igual que la compañía."""
    tid = current_terminal.get()
    if tid is None:
        raise SinCompania("Se pidió la terminal actual y no hay ninguna en el contexto.")
    return tid


def sin_filtro(consulta):
    """Marca una consulta como «cruza compañías a propósito».

    Se usa en tres sitios y en ninguno más: el login —que lee `users` antes de
    que exista compañía—, el panel de soporte (F3) y los guiones de
    mantenimiento. Escrito así queda en el `git grep`.
    """
    return consulta.execution_options(**{SIN_FILTRO: True})


def _toca_negocio(state) -> bool:
    """¿La consulta lee alguna tabla de negocio?

    Se pregunta antes de exigir compañía porque exigirla en TODA consulta
    obligaría a marcar con `sin_filtro` el login y cualquier lectura de
    identidad —que no tienen `company_id` y no pueden filtrar por él—. La marca
    dejaría de significar «acá se cruzan compañías a propósito», que es lo único
    que la hace útil al leer el código.
    """
    return any(
        isinstance(mapper.class_, type) and issubclass(mapper.class_, TenantMixin)
        for mapper in state.all_mappers
    )


@event.listens_for(Session, "do_orm_execute")
def _filtrar_por_compania(state) -> None:
    if not state.is_select:
        # Los UPDATE y DELETE del ORM no pasan por acá. Van con su filtro
        # escrito a mano; está anotado como riesgo en plan §10.
        return

    if state.execution_options.get(SIN_FILTRO):
        return

    if not _toca_negocio(state):
        return

    cid = current_company.get()
    if cid is None:
        raise SinCompania(
            "Consulta a una tabla de negocio sin compañía en el contexto. "
            "Falta la dependencia que fija la compañía, o la consulta cruza "
            "compañías y debe pedirlo con sin_filtro()."
        )

    state.statement = state.statement.options(
        with_loader_criteria(
            TenantMixin,
            # El `cid` del cierre viaja como parámetro ligado, no se hornea en
            # la consulta en caché: SQLAlchemy rastrea las variables del cierre
            # de estas lambdas justo para esto.
            lambda cls: cls.company_id == cid,
            include_aliases=True,
        )
    )


@event.listens_for(Session, "before_flush")
def _sellar_compania(session: Session, flush_context, instances) -> None:
    """Le pone la compañía a toda fila nueva de negocio.

    Es la otra mitad del filtro de arriba, y por la misma razón. Si leer sin
    `WHERE company_id` es imposible pero escribir sin `company_id` depende de
    que quince sitios se acuerden, el aislamiento se rompe por el lado de
    escritura: una venta guardada sin compañía queda visible para nadie —o,
    peor, para quien tenga ese número— y el defecto aparece semanas después.

    No pisa lo que ya venga puesto: los guiones de mantenimiento y las semillas
    crean filas de una compañía distinta de la del contexto a propósito.
    """
    for objeto in session.new:
        if not isinstance(objeto, TenantMixin):
            continue
        if objeto.company_id is not None:
            continue

        cid = current_company.get()
        if cid is None:
            raise SinCompania(
                f"Se intentó guardar {type(objeto).__name__} sin compañía. "
                f"Ni la fila la trae ni hay una en el contexto de la petición."
            )
        objeto.company_id = cid
