"""
Hacienda se nombra en un solo sitio (T-613, plan §7.1 y §10).

Es la mitigación **comprobable** del riesgo TRIBU-CR: el sistema que reemplaza
a ATV desde octubre de 2025 puede cambiar URLs, realm o `client_id`, y
`docs/hacienda/costa-rica/README.md` §12 deja pendiente confirmar cuánto. Con
ese dominio repartido por el código, el cambio es una cacería por `grep` y lo
que se olvide falla el día de transmitir; con un módulo, es una tabla.

Va como prueba y no como acuerdo, por lo mismo que el resto de los guardianes:
un acuerdo que hay que acordarse de respetar no protege nada. Mismo patrón que
`test_error_codes.py`.

Se lee el texto de los archivos y no se importa nada: importar ejecuta código, y
un módulo que abre la base al importarse haría fallar la prueba por la razón
equivocada.
"""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
APP = RAIZ / "app"

#: El único archivo que puede nombrar a Hacienda.
UNICA_FUENTE = APP / "domain" / "hacienda.py"

#: Lo que se busca. No es la URL entera a propósito: lo que no puede repartirse
#: es **el dominio**, y escribirlo con otra ruta —`/recepcion/v2/`— sería el
#: mismo problema con otra cara.
DOMINIO = "comprobanteselectronicos.go.cr"

#: Los otros datos que decide el ambiente y que también se escaparían de a uno.
#:
#: El realm de producción —`rut` a secas— NO está en la lista y no puede estar:
#: buscar tres letras sueltas caza «rut» dentro de cualquier palabra. Queda
#: cubierto igual, porque vive en la misma tabla que `api-prod`, y esa sí es
#: una cadena que nadie escribe por accidente.
OTROS = ("api-stag", "api-prod", "rut-stag")


def archivos() -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if p != UNICA_FUENTE)


@pytest.mark.parametrize("archivo", archivos(), ids=lambda p: str(p.relative_to(APP)).replace("\\", "/"))
def test_nadie_mas_nombra_a_Hacienda(archivo: Path):
    texto = archivo.read_text(encoding="utf-8")
    for aguja in (DOMINIO, *OTROS):
        assert aguja not in texto, (
            f"{archivo.relative_to(APP)} escribe «{aguja}». Eso vive en "
            f"app/domain/hacienda.py y se pide con `endpoints(ambiente)`: el día "
            f"que TRIBU-CR lo mueva, hay que poder cambiarlo en un solo lugar."
        )


def test_y_el_modulo_de_verdad_lo_tiene():
    """La prueba de la prueba.

    Sin esto, borrar las URLs del módulo dejaría la batería entera en verde: no
    habría nada escrito en ninguna parte, que es lo que esta prueba mediría como
    éxito perfecto.
    """
    texto = UNICA_FUENTE.read_text(encoding="utf-8")
    for aguja in (DOMINIO, *OTROS):
        assert aguja in texto, f"app/domain/hacienda.py ya no dice «{aguja}»"
