"""Los límites del plan (RF-12).

Un plan no es una lista de precios sino lo que el sistema deja hacer: cuántas
sucursales, cuántas cajas, cuánta gente. Acá está la aritmética de eso y nada
más —contar las que hay es trabajo de una consulta, y decidir qué hacer cuando
no cabe es del router—.

Los tres recursos que se cuentan son los del plan: `plans.max_sucursales`,
`plans.max_terminales`, `plans.max_usuarios`.

**Un máximo en 0 bloquea; uno negativo no limita.** Es la parte que hay que
decidir a mano, porque «0» es lo que queda cuando alguien inserta un plan sin
llenar las columnas y también lo que escribiría quien quiere decir «ilimitado».
Se elige que 0 bloquee: un plan a medio configurar impide crear una caja de más
—molesto, visible, se arregla en un minuto— en vez de regalar el producto sin
que nadie se entere. Quien de verdad quiera un plan sin techo escribe −1, que
no se teclea por accidente.
"""

from __future__ import annotations

#: Lo que se escribe en el plan para decir «sin techo». Explícito a propósito:
#: ver el porqué en el encabezado.
SIN_LIMITE = -1

#: Los recursos que un plan limita, con el nombre que viaja al POS en los datos
#: del error. Van en inglés como el resto del contrato del API.
RECURSOS: tuple[str, ...] = ("branches", "terminals", "users")


def sin_limite(maximo: int) -> bool:
    """¿Este máximo significa «los que quiera»?"""
    return maximo < 0


def hay_lugar(actuales: int, maximo: int) -> bool:
    """¿Cabe uno más?

    `actuales` es cuántos hay ya. Se compara con `>=` y no con `>` porque el que
    se está creando todavía no está contado: con el máximo en 3 y tres
    existentes, el cuarto no cabe.
    """
    return sin_limite(maximo) or actuales < maximo


def cupo(actuales: int, maximo: int) -> int | None:
    """Cuántos más se pueden crear. `None` es «sin límite».

    Sirve para mostrar «3 de 5» en el panel de soporte sin que la pantalla tenga
    que repetir la aritmética. Nunca devuelve negativo: un plan que se recortó
    después de haber creado de más queda en 0, no en −2, porque lo que
    significa es «ninguno más», y los que ya existen no se borran por eso.
    """
    if sin_limite(maximo):
        return None
    return max(0, maximo - actuales)
