"""Qué módulos incluye un plan (RN-49 a RN-51, QA-01).

Desde QA-01 **cada sección del POS es un módulo** —ventas, caja, facturas,
devoluciones, reportes, inventario, compras, proveedores, contabilidad,
planilla, clientes y usuarios— y los planes son **paquetes** de ellos: un
restaurante no necesita caja ni inventario, y un comercio que compra a crédito
necesita compras. Configuración no es un módulo: sin ella no hay negocio.

Lo que decide si una compañía los tiene es **su plan**, y no un interruptor
propio: dos sitios para la misma verdad es donde se separan, y el día que
discrepen nadie sabría cuál manda. Se decidió así con el usuario al hacer los
paquetes (2026-10-03).

Acá vive lo que es regla y no consulta: cuáles son los módulos que existen y
qué significa que un plan incluya uno. Leer la fila del plan es trabajo del
adaptador (`crud_membership.modulos_de`), y aplicarlo, de la dependencia
`auth_dependency.require_module`.

**Un módulo apagado no esconde nada: impide escribir** (RN-50). Los libros de
una compañía que bajó de plan siguen siendo su respaldo ante Hacienda y las
boletas de una planilla siguen siendo la prueba de lo pagado. Esa mitad de la
regla no está en este archivo porque no es una propiedad del plan sino del
método de la petición, y vive donde ya vive la del vencimiento.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .errors import UnknownModule

#: Los módulos que existen, en el orden del menú. El nombre es el de la columna
#: de `plans` y el que viaja al POS, así que va en inglés.
#:
#: `factura_electronica` **no** está acá aunque también sea una bandera del plan:
#: es de la 002, su nombre está en español y nadie la consume todavía.
MODULES: tuple[str, ...] = (
    "sales",
    "cash",
    "invoices",
    "returns",
    "reports",
    "inventory",
    "purchases",
    "suppliers",
    "accounting",
    "payroll",
    "clients",
    "users",
)

#: Lo que el POS tuvo siempre, antes de que sus secciones fueran módulos. Es lo
#: que lleva un plan que se crea sin decir más (`bootstrap.py`) y lo que la
#: migración 022 les deja encendido a los planes que ya existían: nadie pierde
#: una sección por actualizar el sistema.
BASE: tuple[str, ...] = (
    "sales",
    "cash",
    "invoices",
    "returns",
    "reports",
    "inventory",
    "clients",
    "users",
)

_COMERCIO: tuple[str, ...] = (
    "sales",
    "cash",
    "invoices",
    "returns",
    "inventory",
    "suppliers",
    "clients",
    "users",
)

#: Los paquetes que se venden (QA-01), por el nombre del plan. La migración 022
#: los da de alta si no existe un plan con ese nombre; uno que ya existía
#: conserva lo suyo y se ajusta desde Planes.
PACKAGES: dict[str, tuple[str, ...]] = {
    "Restaurante": ("sales", "invoices", "clients", "users"),
    "Comercio": _COMERCIO,
    "Comercio con compras": (*_COMERCIO, "reports", "purchases"),
    "Completo": MODULES,
}


@dataclass(frozen=True)
class Modules:
    """Los módulos de un plan.

    Apagados por omisión, y no es una comodidad de construcción: un plan del que
    no se sabe nada no incluye nada. Falla cerrado, igual que el filtro de
    compañía y que la suscripción sin fecha.
    """

    sales: bool = False
    cash: bool = False
    invoices: bool = False
    returns: bool = False
    reports: bool = False
    inventory: bool = False
    purchases: bool = False
    suppliers: bool = False
    accounting: bool = False
    payroll: bool = False
    clients: bool = False
    users: bool = False

    @classmethod
    def of(cls, names: Iterable[str]) -> Modules:
        """Los que están encendidos, por nombre: un paquete, o lo que se pide al
        crear un plan. Un nombre que no existe revienta, como en `includes`."""
        nombres = tuple(names)
        for nombre in nombres:
            if nombre not in MODULES:
                raise UnknownModule(nombre)
        return cls(**{nombre: True for nombre in nombres})

    def includes(self, module: str) -> bool:
        """¿Incluye este módulo?

        Un nombre que no está en `MODULES` **revienta** en vez de devolver
        `False`. No es una situación del negocio sino un error de quien escribe
        el código —`require_module("purchase")`, en singular—, y devolver
        `False` lo convertiría en un 403 que parece un problema del plan del
        cliente. Se prefiere el error ruidoso en la ruta equivocada al silencio
        en todas.
        """
        if module not in MODULES:
            raise UnknownModule(module)
        return bool(getattr(self, module))

    def as_dict(self) -> dict[str, bool]:
        """Para el POS, que arma la navegación con esto (RF-40).

        Se devuelven todos siempre, también los apagados: una clave ausente
        y una en `false` se leen distinto en JavaScript, y la pantalla tiene que
        poder distinguir «no lo tiene» de «no vino el dato».
        """
        return {nombre: bool(getattr(self, nombre)) for nombre in MODULES}
