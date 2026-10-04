"""Genera el catálogo de ubicaciones del backend y del POS (T-722, RN-83).

La fuente es `normativa/Codificacionubicacion_V4.4.xlsx`, la «nota 14» del
anexo: Hacienda la publica aparte, en la página de anexos y estructuras de ATV,
como `Codificacionubicacion_V4.4.rar`. El anexo no la trae adentro.

Salen dos archivos con los mismos datos, porque son dos aplicaciones que no se
ven: el backend valida lo que se guarda y el POS arma los desplegables y el
simulado. Los dos se **generan**, no se editan: cuando Hacienda publique otra
versión, se reemplaza el Excel y se corre esto de nuevo.

    python docs/hacienda/costa-rica/generar_ubicaciones.py

El Excel trae también los barrios, pero en la 4.4 el barrio dejó de ser un
código: es texto libre de 5 a 50 caracteres. Por eso no se generan.
"""

from __future__ import annotations

import json
from pathlib import Path

import openpyxl

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
FUENTE = AQUI / "normativa" / "Codificacionubicacion_V4.4.xlsx"
BACKEND = RAIZ / "backend" / "app" / "domain" / "locations_data.py"
POS = RAIZ / "frontend" / "src" / "lib" / "domain" / "locationsData.ts"

#: Palabras que van en minúscula dentro de un nombre: «San Rafael de Heredia».
MENORES = {"de", "del", "la", "las", "los", "el", "y", "e"}


def _titulo(nombre: str) -> str:
    """Un nombre que solo viene en mayúsculas, escrito como los demás."""
    palabras = nombre.strip().lower().split()
    return " ".join(
        p if (i and p in MENORES) else p[:1].upper() + p[1:] for i, p in enumerate(palabras)
    )


def _nombre(variantes: set[str]) -> str:
    """El Excel repite cada nombre en mayúsculas en la primera fila de su grupo.

    Se prefiere la variante escrita normal; si solo existe la de mayúsculas, se
    pasa a título.
    """
    normales = sorted(v.strip() for v in variantes if not v.isupper())
    if normales:
        return normales[0]
    return _titulo(sorted(variantes)[0])


def leer() -> tuple[dict, dict, dict]:
    libro = openpyxl.load_workbook(FUENTE, read_only=True)
    hoja = libro.worksheets[0]
    provincias: dict[str, set[str]] = {}
    cantones: dict[tuple[str, str], set[str]] = {}
    distritos: dict[tuple[str, str, str], set[str]] = {}
    for i, fila in enumerate(hoja.iter_rows(values_only=True)):
        if i == 0:
            continue
        _, p, pn, c, cn, d, dn = fila[:7]
        if p is None:
            continue
        # Algunos códigos vienen como texto («'6'») y el resto como número.
        p, c, d = str(int(p)), f"{int(c):02d}", f"{int(d):02d}"
        provincias.setdefault(p, set()).add(str(pn))
        cantones.setdefault((p, c), set()).add(str(cn))
        distritos.setdefault((p, c, d), set()).add(str(dn))

    prov = {p: _nombre(n) for p, n in sorted(provincias.items())}
    cant: dict[str, dict[str, str]] = {}
    for (p, c), n in sorted(cantones.items()):
        cant.setdefault(p, {})[c] = _nombre(n)
    dist: dict[str, dict[str, str]] = {}
    for (p, c, d), n in sorted(distritos.items()):
        dist.setdefault(f"{p}-{c}", {})[d] = _nombre(n)
    return prov, cant, dist


CABECERA = (
    "División territorial de Hacienda: la nota 14 del anexo, "
    "`Codificacionubicacion_V4.4`.\n\n"
    "**Generado** por `docs/hacienda/costa-rica/generar_ubicaciones.py` a partir "
    "del Excel oficial. No se edita a mano: se regenera."
)


def _py(prov: dict, cant: dict, dist: dict) -> str:
    def bloque(nombre: str, tipo: str, valor: dict) -> str:
        cuerpo = json.dumps(valor, ensure_ascii=False, indent=4)
        return f"{nombre}: Final[{tipo}] = {cuerpo}\n"

    return (
        f'"""{CABECERA}\n\nLas llaves de `DISTRICTS` son «provincia-cantón»: `"1-01"`.\n"""\n\n'
        "from typing import Final\n\n"
        + bloque("PROVINCES", "dict[str, str]", prov)
        + "\n"
        + bloque("CANTONS", "dict[str, dict[str, str]]", cant)
        + "\n"
        + bloque("DISTRICTS", "dict[str, dict[str, str]]", dist)
    )


def _ts(prov: dict, cant: dict, dist: dict) -> str:
    def bloque(nombre: str, tipo: str, valor: dict) -> str:
        cuerpo = json.dumps(valor, ensure_ascii=False, indent="\t")
        return f"export const {nombre}: {tipo} = {cuerpo};\n"

    comentario = "\n".join(f" * {linea}".rstrip() for linea in CABECERA.split("\n"))
    return (
        f"/**\n{comentario}\n *\n * Las llaves de `DISTRICTS` son «provincia-cantón»: `'1-01'`.\n */\n\n"
        + bloque("PROVINCES", "Readonly<Record<string, string>>", prov)
        + "\n"
        + bloque("CANTONS", "Readonly<Record<string, Readonly<Record<string, string>>>>", cant)
        + "\n"
        + bloque("DISTRICTS", "Readonly<Record<string, Readonly<Record<string, string>>>>", dist)
    )


def main() -> None:
    prov, cant, dist = leer()
    BACKEND.write_text(_py(prov, cant, dist), encoding="utf-8", newline="\n")
    POS.write_text(_ts(prov, cant, dist), encoding="utf-8", newline="\n")
    total = sum(len(v) for v in dist.values())
    print(f"{len(prov)} provincias, {sum(len(v) for v in cant.values())} cantones, {total} distritos")


if __name__ == "__main__":
    main()
