"""El estado de la suscripción, en aritmética pura (RF-10, RF-11, RN-1, RN-2).

Es la regla que decide si una compañía puede entrar y si puede vender. Vive en
`domain/` porque es una función de tres datos —el estado guardado, la fecha de
vencimiento y el día de hoy— y de nada más: ni base de datos, ni petición, ni
reloj propio. La fecha entra como argumento justamente para que la prueba pueda
pararse en el día que quiera.

Los cinco estados y qué se puede hacer en cada uno están en spec §2. Acá se
agregan los dos matices que la tabla no puede expresar en una celda:

* **El vencimiento se deriva de la fecha, no de que alguien cambie el estado.**
  Una compañía `activa` cuya fecha ya pasó está vencida, aunque nadie haya
  tocado la columna. La alternativa —esperar a que soporte marque el estado a
  mano— convierte el cobro en un trabajo diario y deja de cobrar el día que
  nadie mire. El estado guardado sigue siendo el que soporte puso; lo que esta
  función devuelve es el **efectivo**.

* **La gracia se cuenta desde la fecha de vencimiento** y dura siete días
  (`DIAS_DE_GRACIA`), contando el primero después de vencer. Dentro de la
  gracia se vende con un aviso rojo permanente; pasada, el sistema queda en
  solo lectura. Cerrar una caja abierta se puede siempre (RN-1), y esa
  excepción no está acá sino en la única puerta que la necesita:
  `auth_dependency.ESCRITURA_EN_SOLO_LECTURA`.

Sin fecha de vencimiento no hay gracia que calcular, y entonces no hay gracia:
falla cerrado, igual que el filtro de compañía. Una compañía marcada `vencida`
sin fecha queda en solo lectura, que es lo peor que puede pasarle a quien
olvidó escribir un dato —y no «vende gratis para siempre», que es lo peor que
puede pasarle al negocio—.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

#: Los cinco estados de spec §2. El orden es el del ciclo de vida.
ESTADOS: tuple[str, ...] = ("prueba", "activa", "vencida", "suspendida", "cancelada")

#: Días que se sigue vendiendo después de vencer, contando el primero después
#: de la fecha. Perder una venta por un pago que entra mañana es peor negocio
#: que cobrar una semana tarde.
DIAS_DE_GRACIA = 7

#: Desde cuándo se avisa que la suscripción vence (RF-11). Una semana alcanza
#: para hacer una transferencia sin que el aviso se vuelva parte del paisaje.
DIAS_DE_AVISO = 7

#: Estados en los que la puerta abre. `vencida` abre a propósito: el bloqueo por
#: no pagar es dejar de vender, no dejar de entrar —los datos siguen siendo del
#: cliente y tiene que poder consultarlos y cerrar su caja—.
ESTADOS_QUE_ENTRAN: tuple[str, ...] = ("prueba", "activa", "vencida")

#: Con la suscripción suspendida solo entra el administrador, y solo para ver el
#: aviso de pago. Al cajero no se le puede pedir que arregle una factura.
ESTADO_SOLO_ADMIN = "suspendida"


@dataclass(frozen=True)
class Suscripcion:
    """Qué se puede hacer hoy con esta compañía.

    `aviso` es un **código**, no una frase (RN-30): el dominio no escribe texto
    para personas. La oración la arma el POS con los datos de acá.
    """

    #: El estado efectivo: el guardado, o `vencida` si la fecha ya pasó.
    estado: str
    #: El que está en la base. Se devuelve para que el panel de soporte muestre
    #: lo que alguien puso, no lo que el sistema dedujo.
    guardado: str
    vence_el: date | None
    #: Días hasta el vencimiento. Positivo faltan, 0 vence hoy, negativo pasó.
    #: `None` cuando no hay fecha.
    dias: int | None
    #: Días de gracia que quedan, contando hoy. 0 = ya no se vende.
    gracia: int
    puede_entrar: bool
    #: Si no, el sistema queda en solo lectura: se consulta y se cierra la caja.
    puede_vender: bool
    aviso: str | None


def dias_restantes(vence_el: date | None, hoy: date) -> int | None:
    """Días hasta el vencimiento. Negativo si ya pasó, `None` si no hay fecha."""
    if vence_el is None:
        return None
    return (vence_el - hoy).days


def estado_efectivo(guardado: str, vence_el: date | None, hoy: date) -> str:
    """El estado que manda hoy.

    Solo `prueba` y `activa` se degradan por fecha. `suspendida` y `cancelada`
    son decisiones de soporte y no las mueve el calendario; `vencida` ya lo
    está.
    """
    if guardado not in ("prueba", "activa"):
        return guardado

    dias = dias_restantes(vence_el, hoy)
    if dias is not None and dias < 0:
        return "vencida"
    return guardado


def _gracia(dias: int | None) -> int:
    """Días de gracia que quedan, contando hoy.

    `dias` es lo que devuelve `dias_restantes`, así que el primer día después de
    vencer vale −1 y la cuenta da los siete completos. Se topa en
    `DIAS_DE_GRACIA` para que marcar `vencida` con la fecha en el futuro no
    regale una semana extra: la cuenta empieza cuando la fecha pasa.
    """
    if dias is None:
        return 0
    return max(0, min(DIAS_DE_GRACIA, DIAS_DE_GRACIA + dias + 1))


def _aviso(estado: str, guardado: str, dias: int | None, gracia: int) -> str | None:
    """Qué tiene que decir la pantalla, en código."""
    if estado == "cancelada":
        return "cancelada"
    if estado == "suspendida":
        return "suspendida"
    if estado == "vencida":
        return "en_gracia" if gracia > 0 else "solo_lectura"
    if dias is not None and dias <= DIAS_DE_AVISO:
        return "vence_pronto"
    # Una prueba avisa siempre el día en que vence, aunque falte un mes: es
    # información que la persona necesita para decidir si sigue (spec §2).
    if guardado == "prueba":
        return "en_prueba"
    return None


def evaluar(
    guardado: str, vence_el: date | None, hoy: date, rol: str = "admin"
) -> Suscripcion:
    """Todo lo que hay que saber del estado de una compañía, en un solo objeto.

    `rol` solo cambia una cosa: con la suscripción suspendida entra el
    administrador y no el cajero. Se pasa acá y no se resuelve afuera para que
    la regla viva en un solo sitio; por omisión es `admin`, que es el caso de
    quien pregunta sin tener a nadie en frente —el panel de soporte—.

    Un estado que no esté en `ESTADOS` **no entra**. Es deliberado: un error de
    dedo en la base cierra la puerta en vez de abrirla.
    """
    estado = estado_efectivo(guardado, vence_el, hoy)
    dias = dias_restantes(vence_el, hoy)
    gracia = _gracia(dias) if estado == "vencida" else 0

    if estado == ESTADO_SOLO_ADMIN:
        puede_entrar = rol == "admin"
    else:
        puede_entrar = estado in ESTADOS_QUE_ENTRAN

    puede_vender = estado in ("prueba", "activa") or (estado == "vencida" and gracia > 0)

    return Suscripcion(
        estado=estado,
        guardado=guardado,
        vence_el=vence_el,
        dias=dias,
        gracia=gracia,
        puede_entrar=puede_entrar,
        puede_vender=puede_vender,
        aviso=_aviso(estado, guardado, dias, gracia),
    )


def motivo_de_bloqueo(suscripcion: Suscripcion) -> str | None:
    """Por qué no entra, en código. `None` si entra.

    El motivo es el estado efectivo y no una explicación: quien lo recibe es el
    POS, que tiene la frase en su catálogo para los cinco casos.
    """
    return None if suscripcion.puede_entrar else suscripcion.estado
