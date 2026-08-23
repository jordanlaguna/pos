"""En qué idioma se le habla a quien entra (RN-28, plan §8.4).

Dos niveles y un orden: **lo que eligió la persona, si no lo de la compañía, si
no español**. La compañía lo fija al darse de alta, para que el administrador de
una nueva no arranque en el idioma equivocado; la persona puede cambiarlo para
su sesión, porque un negocio costarricense puede contratar a una cajera
nicaragüense que prefiera otra cosa.

Es una regla y no una consulta, así que vive acá: se prueba sin base de datos y
la usa quien emite el token. Lo que el idioma **no** decide es el idioma del
documento impreso (RN-29): esa es otra columna y otra decisión.
"""

from __future__ import annotations

#: Los idiomas que el POS tiene en catálogo. Es la misma lista de
#: `project.inlang/settings.json` del frontend, y tiene que serlo: un `locale`
#: que el POS no compiló saldría en pantalla como el idioma base sin avisar.
SUPPORTED_LOCALES: tuple[str, ...] = ("es", "en", "pt")

#: El idioma base. Coincide con `baseLocale` del frontend por la misma razón.
DEFAULT_LOCALE = "es"


def normalize_locale(value: object) -> str | None:
    """Un locale utilizable, o `None`.

    Acepta lo que venga de la base sin confiar en su forma: espacios, mayúsculas
    o `es-CR` en una columna que se declaró de cinco caracteres. Lo que no está
    en la lista se descarta en vez de propagarse —un `fr` guardado a mano no
    debe convertirse en una pantalla a medio traducir—.
    """
    if not isinstance(value, str):
        return None
    limpio = value.strip().lower().replace("_", "-")
    if limpio in SUPPORTED_LOCALES:
        return limpio
    # `es-CR`, `pt-BR`: el POS tiene un catálogo por idioma, no por región.
    raiz = limpio.split("-")[0]
    return raiz if raiz in SUPPORTED_LOCALES else None


def effective_locale(user_locale: object, company_locale: object) -> str:
    """El idioma de la sesión: el de la persona, si no el de la compañía, si no `es`."""
    return normalize_locale(user_locale) or normalize_locale(company_locale) or DEFAULT_LOCALE
