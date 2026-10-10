"""
La ficha del producto: qué se escribe en ella y qué no (F15, T-1502).

Dos reglas que vivían en el adaptador y pasan acá con su prueba:

1. **El código de tarifa manda sobre la tarifa** (RN-76). De un código sale
   siempre un porcentaje; del porcentaje no siempre sale un código. Guardar
   los dos por separado es cómo se desincronizan.
2. **En casi todo el formulario un nulo significa «no mandé este campo»**, y
   por eso un PUT parcial no borra el resto. En cuatro columnas no: ahí el nulo
   **es** el valor —«sin clasificar», «la tasa configurada»— y la cadena vacía
   es ese nulo (RN-9).

Y una tercera, nueva: **la existencia no se edita desde la ficha** (RN-98).
"""

from __future__ import annotations

from .errors import StockNotEditable
from .fe_tax_codes import check_code, rate_for

#: Columnas donde el nulo **es un valor**, no «no lo mandé» (RN-9).
#:
#: `tax_rate` en nulo significa «la tasa configurada del negocio»: es lo que
#: tienen los productos que nadie ha clasificado. Sin esta lista, clasificar un
#: producto una vez sería una puerta de una sola dirección. En el resto de las
#: columnas la regla contraria es la correcta —`name=None` pondría el nombre en
#: NULL y la columna no lo admite—, y por eso la lista es corta y explícita.
CLEARABLE: frozenset[str] = frozenset({"cabys_code", "tax_rate", "tax_code", "tariff_heading"})


def resolve_tax(tax_code: object, tax_rate: float | None) -> tuple[str | None, float | None]:
    """`(código, tarifa)` con los que se guarda el producto (RN-76).

    Con código de Hacienda la tarifa sale de él; sin código, de lo que mande el
    POS, incluido el nulo. Un código inválido lanza `InvalidTaxCode`.
    """
    if tax_code:
        codigo = check_code(tax_code)
        return codigo, float(rate_for(codigo).value)
    return None, tax_rate


def clean_changes(product_id: int, changes: dict) -> dict:
    """Lo que un PUT parcial cambia de verdad.

    Se salta los nulos que significan «no lo mandé», convierte la cadena vacía
    de las `CLEARABLE` en el nulo que es, y rechaza `stock`: la existencia se
    mueve, no se edita (RN-98). Un cliente viejo que la mande recibe el «no»
    que le dice por dónde sí.
    """
    if changes.get("stock") is not None:
        raise StockNotEditable(product_id)

    limpio: dict = {}
    for clave, valor in changes.items():
        if clave == "stock":
            continue
        if valor is None and clave not in CLEARABLE:
            continue
        if valor == "" and clave in CLEARABLE:
            valor = None
        limpio[clave] = valor
    return limpio
