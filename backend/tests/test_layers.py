"""
La regla de dependencias, comprobada (T-114).

Las capas apuntan hacia adentro. `domain` no importa nada de fuera;
`application` habla con puertos; `infrastructure` e `interfaces` son los
adaptadores y pueden importar lo que necesiten.

Va como prueba y no como guion suelto a propósito: un guion que hay que
acordarse de correr no protege nada. Acá cualquier import que rompa la regla
tumba `pytest`, que es la verificación que ya se corre al terminar.

Se lee el árbol de sintaxis y no se importa cada módulo: importar ejecuta el
código, y un módulo que abre la base al importarse haría fallar la prueba por la
razón equivocada.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

#: Bibliotecas de fuera que no pueden aparecer en el núcleo. La lista es corta a
#: propósito: son las que de verdad tientan.
EXTERNAS = {
    "sqlalchemy",
    "fastapi",
    "pydantic",
    "starlette",
    "jose",
    "bcrypt",
    "reportlab",
    "requests",
    "dotenv",
    "pymysql",
}

#: Qué puede importar cada capa, además de la biblioteca estándar y de sí misma.
PERMITIDO: dict[str, set[str]] = {
    "domain": set(),
    "application": {"app.domain"},
}


def modulos(capa: str) -> list[Path]:
    return sorted((APP / capa).rglob("*.py"))


def imports_de(archivo: Path) -> list[tuple[str, int]]:
    """Cada módulo importado, con la línea. `from x.y import z` cuenta como `x.y`."""
    arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
    encontrados: list[tuple[str, int]] = []

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                encontrados.append((alias.name, nodo.lineno))
        elif isinstance(nodo, ast.ImportFrom):
            # `from .errors import X` dentro de la capa: relativo, siempre propio.
            if nodo.level:
                continue
            if nodo.module:
                encontrados.append((nodo.module, nodo.lineno))

    return encontrados


def raiz(modulo: str) -> str:
    return modulo.split(".")[0]


def es_estandar(modulo: str) -> bool:
    return raiz(modulo) in sys.stdlib_module_names


def casos(capa: str):
    return [pytest.param(p, id=str(p.relative_to(APP)).replace("\\", "/")) for p in modulos(capa)]


# --------------------------------------------------------------------- dominio


@pytest.mark.parametrize("archivo", casos("domain"))
def test_el_dominio_no_importa_nada_de_fuera(archivo: Path):
    """
    Si para probar una regla hay que levantar la base, la regla está en la capa
    equivocada. Esta prueba es lo que impide que eso pase sin que nadie lo note.
    """
    for modulo, linea in imports_de(archivo):
        if es_estandar(modulo):
            continue
        assert modulo.startswith("app.domain"), (
            f"{archivo.name}:{linea} importa «{modulo}». El dominio solo puede "
            f"importar la biblioteca estándar y a sí mismo."
        )


# ------------------------------------------------------------------ aplicación


@pytest.mark.parametrize("archivo", casos("application"))
def test_la_aplicacion_no_conoce_la_persistencia_ni_HTTP(archivo: Path):
    for modulo, linea in imports_de(archivo):
        if es_estandar(modulo):
            continue

        assert raiz(modulo) not in EXTERNAS, (
            f"{archivo.name}:{linea} importa «{modulo}». Los casos de uso hablan "
            f"con puertos; quien conoce {raiz(modulo)} es un adaptador."
        )

        propio = modulo.startswith("app.application")
        permitido = any(modulo.startswith(p) for p in PERMITIDO["application"])
        assert propio or permitido, (
            f"{archivo.name}:{linea} importa «{modulo}». La aplicación solo puede "
            f"importar el dominio y a sí misma."
        )


# ---------------------------------------------------------------- transversales


def test_ninguna_capa_de_adentro_importa_una_de_afuera():
    """Dicho al revés, por si alguna carpeta nueva se salta las de arriba."""
    afuera = ("app.infrastructure", "app.router", "app.services", "app.models", "app.schemas")

    for capa in ("domain", "application"):
        for archivo in modulos(capa):
            for modulo, linea in imports_de(archivo):
                assert not modulo.startswith(afuera), (
                    f"{capa}/{archivo.name}:{linea} importa «{modulo}»: la "
                    f"dependencia apunta hacia afuera."
                )


def test_las_dos_capas_de_adentro_existen_y_tienen_algo():
    # Si alguien borra la carpeta, las pruebas de arriba pasarían por vacías.
    for capa in ("domain", "application"):
        archivos = [p for p in modulos(capa) if p.name != "__init__.py"]
        assert archivos, f"app/{capa}/ está vacía"
