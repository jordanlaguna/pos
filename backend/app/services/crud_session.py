"""Emitir el token de sesión.

Vive en un servicio y no en el router del login porque **hay más de un sitio que
emite sesión**: el login, la elección de compañía y, desde T-810, cambiar de
idioma. Todos tienen que producir exactamente el mismo token; si cada uno lo
armara por su cuenta, el día que se agregue un reclamo alguno se quedaría sin él
y el síntoma aparecería en otra parte.

Desde F3 emite además los dos de soporte: el del panel y el de *entrar como*.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.domain.locale import effective_locale
from app.models.model_company import Company
from app.models.model_user import User
from app.services import crud_membership
from app.utils.auth_dependency import TIPO_SESION, TIPO_SOPORTE, TIPO_SUPLANTACION
from app.utils.jwt_handler import create_access_token

#: Cuánto dura un *entrar como* (RF-8). Corto a propósito: es una visita para
#: diagnosticar, no una sesión. Media hora alcanza para mirar una configuración
#: y reproducir un problema, y si hace falta más se vuelve a entrar —dejando
#: otra línea en la bitácora, que es justamente lo que se quiere—.
MINUTOS_DE_SUPLANTACION = 30

#: Lo que se guarda del motivo en el token. La bitácora lleva el texto completo
#: (500 caracteres); acá va recortado porque el token viaja en una cookie y en
#: cada cabecera `Authorization`, y lo único que hace es que la franja de la
#: pantalla pueda decir por qué se entró.
MOTIVO_EN_EL_TOKEN = 120


def token_de_sesion(db: Session, user: User, company: Company, rol: str) -> str:
    """El token de sesión: quién, dónde, con qué rol y en qué idioma.

    Sucursal y terminal viajan acá y no en cada petición porque son justo lo que
    el cliente no puede elegir (RN-14). Que estén en el token también es lo que
    permite que un cambio de compañía cambie de sucursal sin nada más.

    El idioma va por el mismo camino y por la misma razón (plan §8.4): lo resuelve
    el servidor —lo de la persona, si no lo de la compañía, si no español— y así
    la pantalla no tiene que preguntarlo ni el cliente puede elegirlo. Cambia
    cuando se emite un token nuevo, y por eso cambiar de idioma emite uno.

    **Se llama antes de `commit`.** Después, SQLAlchemy expira los objetos y leer
    `company.locale` dispararía una relectura que, sin compañía en el contexto,
    falla.
    """
    sucursal, terminal = crud_membership.sucursal_y_terminal(db, company.id)
    return create_access_token(
        data={
            "id_user": user.id_user,
            "email": user.email,
            "cid": company.id,
            "bid": sucursal,
            "tid": terminal,
            "rol": rol,
            "loc": effective_locale(user.locale, company.locale),
            "tipo": TIPO_SESION,
        }
    )


def token_de_soporte(user: User) -> str:
    """El token del panel de soporte (T-301, RN-4).

    **Sin `cid`, y eso es todo el diseño.** Soporte no pertenece a ninguna
    compañía, así que su token no lleva ninguna, así que el filtro de
    `tenancy.py` le hace fallar cerrado cualquier consulta a una tabla de
    negocio. Para ver los datos de un cliente tiene que *entrar como* esa
    compañía, que es lo que pide RN-4 y lo que deja rastro en la bitácora.

    El idioma sale de lo que la persona haya elegido, y si no, español: no hay
    compañía de la que heredarlo.
    """
    return create_access_token(
        data={
            "id_user": user.id_user,
            "email": user.email,
            "loc": effective_locale(user.locale, None),
            "tipo": TIPO_SOPORTE,
        }
    )


def token_de_suplantacion(db: Session, user: User, company: Company, motivo: str) -> str:
    """*Entrar como* una compañía (RF-8, RN-4).

    Lleva la compañía destino —con su sucursal y su terminal, para que las
    pantallas que las necesitan funcionen— y dura media hora. El rol no viaja:
    lo pone `auth_dependency` en `admin`, porque un token que dijera su propio
    rol sería un token que se puede editar para decir otro… y aunque va firmado,
    escribir el rol en dos sitios es la forma de que un día digan cosas
    distintas.

    El motivo viaja recortado para que la franja de la pantalla pueda mostrarlo
    sin volver a preguntar. El completo queda en la bitácora, que es donde se
    consulta después.

    Se llama **antes** del commit, igual que `token_de_sesion` y por lo mismo:
    después, leer `company.locale` sería una relectura sin compañía en el
    contexto.
    """
    sucursal, terminal = crud_membership.sucursal_y_terminal(db, company.id)
    return create_access_token(
        data={
            "id_user": user.id_user,
            "email": user.email,
            "cid": company.id,
            "bid": sucursal,
            "tid": terminal,
            "loc": effective_locale(user.locale, company.locale),
            "mot": motivo[:MOTIVO_EN_EL_TOKEN],
            "tipo": TIPO_SUPLANTACION,
        },
        expires_delta=timedelta(minutes=MINUTOS_DE_SUPLANTACION),
    )
