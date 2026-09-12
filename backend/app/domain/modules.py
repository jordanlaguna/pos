"""Qué módulos incluye un plan (RN-49 a RN-51).

Compras, contabilidad y planilla se venden aparte del POS. Lo que decide si una
compañía los tiene es **su plan**, y no un interruptor propio: dos sitios para
la misma verdad es donde se separan, y el día que discrepen nadie sabría cuál
manda.

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

from dataclasses import dataclass

from .errors import UnknownModule

#: Los módulos que existen, en el orden en que llegan (F10, F11, F12). El nombre
#: es el de la columna de `plans` y el que viaja al POS, así que va en inglés.
#:
#: `factura_electronica` **no** está acá aunque también sea una bandera del plan:
#: es de la 002, su nombre está en español y nadie la consume todavía. El día que
#: F6 la use se decide si entra a esta lista o se queda aparte.
MODULES: tuple[str, ...] = ("purchases", "accounting", "payroll")


@dataclass(frozen=True)
class Modules:
    """Los módulos de un plan.

    Apagados por omisión, y no es una comodidad de construcción: un plan del que
    no se sabe nada no incluye nada. Falla cerrado, igual que el filtro de
    compañía y que la suscripción sin fecha.
    """

    purchases: bool = False
    accounting: bool = False
    payroll: bool = False

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

        Se devuelven los tres siempre, también los apagados: una clave ausente
        y una en `false` se leen distinto en JavaScript, y la pantalla tiene que
        poder distinguir «no lo tiene» de «no vino el dato».
        """
        return {nombre: bool(getattr(self, nombre)) for nombre in MODULES}
