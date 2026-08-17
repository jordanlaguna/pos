#!/usr/bin/env python3
"""Respaldar, borrar y restaurar **una** compañía (T-225, decidido en T-217).

Con base compartida, devolverle sus datos a un cliente dejó de ser un
`mysqldump`: hay que extraer sus filas de doce tablas respetando el orden de las
claves foráneas. Esto hace eso, y además el camino de vuelta.

    python company_dump.py exportar --afiliado 2 --compania 1 --salida b.json
    python company_dump.py borrar   --afiliado 2 --compania 1 --confirmar 2-1
    python company_dump.py importar --entrada b.json

Sirve para dos cosas distintas, y por eso vale la pena que esté bien hecho:
entregarle los datos a quien se da de baja, y volver atrás cuando una compañía
se daña sin tocar a las demás que están vendiendo en ese momento.

Cómo funciona, y por qué así
----------------------------

**Se conservan los identificadores.** `auto_increment` de MySQL nunca reutiliza
un número, así que las filas de una compañía borrada dejan sus identificadores
libres para siempre y la restauración los puede conservar tal cual. Remapear
claves entre doce tablas es justo donde este tipo de herramienta se rompe.

**Se restaura solo lo que no está.** El precio de lo anterior: importar sobre una
compañía que todavía tiene filas está prohibido, y el guion se niega antes de
tocar nada. Mezclar sería peor que fallar.

**La identidad no es de la compañía.** `users` y `persons` son globales y pueden
estar compartidas con otra compañía que sigue viva, así que **no se borran** al
borrar una compañía: se quedan sin membresía, que es lo correcto. Se exportan
igual —con su id— para poder recrearlas si al restaurar ya no existieran; sin
eso, una venta quedaría apuntando a un usuario que no está.

**El plan es catálogo, no dato del cliente.** Es lo único que se busca por
nombre en vez de por id: los planes son comunes a todas las compañías y el id
que tienen en una instalación no tiene por qué ser el mismo en otra.

Va por SQLAlchemy Core y no por el ORM a propósito: el filtro automático por
compañía (`app/utils/tenancy.py`) escucha las consultas del ORM, y acá se quiere
justamente elegir la compañía a mano, sin que nada la imponga ni la esconda.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, insert, select

from app.database.database import Base, engine

# Los modelos se importan para que `Base.metadata` tenga las tablas; el orden de
# las claves foráneas se declara abajo y no se deduce, para que se pueda leer.
import app.models.model_cash  # noqa: F401
import app.models.model_categories  # noqa: F401
import app.models.model_client  # noqa: F401
import app.models.model_company  # noqa: F401
import app.models.model_person  # noqa: F401
import app.models.model_product  # noqa: F401
import app.models.model_return  # noqa: F401
import app.models.model_sale_details  # noqa: F401
import app.models.model_sales  # noqa: F401
import app.models.model_settings  # noqa: F401
import app.models.model_stock_entry  # noqa: F401
import app.models.model_user  # noqa: F401

FORMATO = 1

#: Tablas de la compañía, **en orden de dependencia**: cada una solo referencia a
#: las de arriba. Se inserta en este orden y se borra al revés. El orden no lo
#: adivina el guion: si alguien agrega una tabla y no la pone acá, no se
#: exporta, y `verificar_cobertura()` lo dice en vez de dejarlo pasar.
TABLAS_DE_COMPANIA = [
    "companies",
    "branches",
    "terminals",
    "user_companies",
    "categories",
    "clients",
    "products",
    "sales",
    "sale_details",
    "returns",
    "return_details",
    "cash_sessions",
    "cash_movements",
    "stock_entries",
    "stock_entry_details",
    "settings",
    "audit_log",
]

#: Identidad: global, compartida, y por eso no se borra con la compañía. Se
#: exporta para poder recrearla si hiciera falta al restaurar.
TABLAS_DE_IDENTIDAD = ["persons", "users"]

#: Las que no son ni una cosa ni la otra. `plans` es catálogo común.
TABLAS_AJENAS = {"plans"}


def _serializar(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        # Texto y no float: un `float` de 10,2 decimales pierde céntimos, y esto
        # es plata que alguien va a volver a leer dentro de un año.
        return {"$decimal": str(valor)}
    if isinstance(valor, datetime):
        return {"$datetime": valor.isoformat()}
    if isinstance(valor, date):
        return {"$date": valor.isoformat()}
    if isinstance(valor, bytes):
        return {"$bytes": valor.hex()}
    return valor


def _deserializar(valor: Any) -> Any:
    if isinstance(valor, dict) and len(valor) == 1:
        clave, contenido = next(iter(valor.items()))
        if clave == "$decimal":
            return Decimal(contenido)
        if clave == "$datetime":
            return datetime.fromisoformat(contenido)
        if clave == "$date":
            return date.fromisoformat(contenido)
        if clave == "$bytes":
            return bytes.fromhex(contenido)
    return valor


def _filas(conexion, tabla, condicion=None) -> list[dict]:
    consulta = select(tabla) if condicion is None else select(tabla).where(condicion)
    return [
        {k: _serializar(v) for k, v in fila._mapping.items()}
        for fila in conexion.execute(consulta)
    ]


def verificar_cobertura() -> None:
    """Ninguna tabla puede quedar fuera sin que alguien lo haya decidido.

    Es lo que impide que la herramienta envejezca en silencio. Una tabla nueva
    que nadie clasificó no se exporta, y una exportación incompleta es peor que
    ninguna: se descubre el día que hace falta restaurar.
    """
    conocidas = set(TABLAS_DE_COMPANIA) | set(TABLAS_DE_IDENTIDAD) | TABLAS_AJENAS
    faltan = sorted(set(Base.metadata.tables) - conocidas)
    if faltan:
        raise SystemExit(
            "Estas tablas no están clasificadas en company_dump.py y por lo tanto "
            f"no se respaldan: {', '.join(faltan)}\n"
            "Agregalas a TABLAS_DE_COMPANIA (en su lugar del orden de claves "
            "foráneas), a TABLAS_DE_IDENTIDAD o a TABLAS_AJENAS."
        )


def _buscar_compania(conexion, afiliado: int, compania: int) -> dict | None:
    companies = Base.metadata.tables["companies"]
    fila = conexion.execute(
        select(companies).where(
            companies.c.afiliado == afiliado, companies.c.compania == compania
        )
    ).first()
    return dict(fila._mapping) if fila else None


# --------------------------------------------------------------------- exportar


def exportar(afiliado: int, compania: int, salida: str) -> None:
    verificar_cobertura()

    with engine.connect() as conexion:
        datos = _buscar_compania(conexion, afiliado, compania)
        if not datos:
            raise SystemExit(f"No existe la compañía afiliado {afiliado} · compañía {compania}.")
        company_id = datos["id"]

        volcado: dict[str, Any] = {
            "formato": FORMATO,
            "afiliado": afiliado,
            "compania": compania,
            "company_id": company_id,
            "nombre": datos["nombre"],
            # El plan va por NOMBRE: es catálogo común y su id puede ser otro en
            # la instalación donde esto se restaure.
            "plan": conexion.execute(
                select(Base.metadata.tables["plans"].c.nombre).where(
                    Base.metadata.tables["plans"].c.id == datos["plan_id"]
                )
            ).scalar(),
            "tablas": {},
            "identidad": {},
        }

        for nombre in TABLAS_DE_COMPANIA:
            tabla = Base.metadata.tables[nombre]
            columna = tabla.c.id if nombre == "companies" else tabla.c.company_id
            volcado["tablas"][nombre] = _filas(conexion, tabla, columna == company_id)

        # Identidad: solo la de las personas que aparecen en los datos de esta
        # compañía. Exportar `users` entero sería entregarle a un cliente la
        # lista de cuentas de todos los demás.
        ids_usuario = {
            fila["user_id"]
            for nombre in ("user_companies", "sales", "returns", "stock_entries", "cash_sessions")
            for fila in volcado["tablas"][nombre]
            if fila.get("user_id") is not None
        }
        users = Base.metadata.tables["users"]
        persons = Base.metadata.tables["persons"]
        volcado["identidad"]["users"] = (
            _filas(conexion, users, users.c.id_user.in_(ids_usuario)) if ids_usuario else []
        )
        ids_persona = {f["id_person"] for f in volcado["identidad"]["users"] if f.get("id_person")}
        volcado["identidad"]["persons"] = (
            _filas(conexion, persons, persons.c.id_person.in_(ids_persona)) if ids_persona else []
        )

    with open(salida, "w", encoding="utf-8") as archivo:
        json.dump(volcado, archivo, ensure_ascii=False, indent=1)

    total = sum(len(f) for f in volcado["tablas"].values())
    print(f"Compañía   afiliado {afiliado} · compañía {compania} — {volcado['nombre']}")
    print(f"Archivo    {salida}")
    print(f"Filas      {total} en {len(TABLAS_DE_COMPANIA)} tablas, "
          f"más {len(volcado['identidad']['users'])} identidades")
    for nombre in TABLAS_DE_COMPANIA:
        cuantas = len(volcado["tablas"][nombre])
        if cuantas:
            print(f"             {nombre:22} {cuantas}")


# ----------------------------------------------------------------------- borrar


def borrar(afiliado: int, compania: int, confirmar: str) -> None:
    """Borra las filas de una compañía. `users` y `persons` **no** se tocan.

    Pide el par afiliado-compañía escrito a mano. No es burocracia: es la única
    operación de acá que destruye datos, y un `--company 2` mal tecleado borra el
    negocio equivocado sin ninguna otra señal.
    """
    verificar_cobertura()
    esperado = f"{afiliado}-{compania}"
    if confirmar != esperado:
        raise SystemExit(
            f"Para borrar hay que confirmar con --confirmar {esperado} "
            f"(se recibió «{confirmar}»)."
        )

    with engine.begin() as conexion:
        datos = _buscar_compania(conexion, afiliado, compania)
        if not datos:
            raise SystemExit(f"No existe la compañía afiliado {afiliado} · compañía {compania}.")
        company_id = datos["id"]

        borradas = {}
        # Al revés del orden de inserción: los hijos antes que los padres, que
        # es lo que las claves foráneas exigen. Si el orden estuviera mal, la
        # base lo diría en vez de dejar huérfanos.
        for nombre in reversed(TABLAS_DE_COMPANIA):
            tabla = Base.metadata.tables[nombre]
            columna = tabla.c.id if nombre == "companies" else tabla.c.company_id
            resultado = conexion.execute(delete(tabla).where(columna == company_id))
            if resultado.rowcount:
                borradas[nombre] = resultado.rowcount

    print(f"Borrada    afiliado {afiliado} · compañía {compania} — {datos['nombre']}")
    for nombre, cuantas in borradas.items():
        print(f"             {nombre:22} {cuantas}")
    print("Identidad  users y persons quedaron intactas: son globales y pueden "
          "estar compartidas.")


# --------------------------------------------------------------------- importar


def importar(entrada: str) -> None:
    verificar_cobertura()

    with open(entrada, encoding="utf-8") as archivo:
        volcado = json.load(archivo)

    if volcado.get("formato") != FORMATO:
        raise SystemExit(
            f"El archivo dice formato {volcado.get('formato')} y este guion lee {FORMATO}."
        )

    company_id = volcado["company_id"]

    with engine.begin() as conexion:
        # Falla cerrado: si queda una sola fila de esa compañía, no se mezcla.
        for nombre in TABLAS_DE_COMPANIA:
            tabla = Base.metadata.tables[nombre]
            columna = tabla.c.id if nombre == "companies" else tabla.c.company_id
            existentes = conexion.execute(
                select(tabla).where(columna == company_id).limit(1)
            ).first()
            if existentes:
                raise SystemExit(
                    f"La compañía {company_id} todavía tiene filas en «{nombre}». "
                    f"Restaurar encima mezclaría datos viejos con nuevos.\n"
                    f"Borrala primero:  python company_dump.py borrar "
                    f"--afiliado {volcado['afiliado']} --compania {volcado['compania']} "
                    f"--confirmar {volcado['afiliado']}-{volcado['compania']}"
                )

        # La identidad primero: las ventas apuntan a usuarios, y si el usuario
        # ya no existiera la clave foránea rechazaría la venta.
        recreadas = 0
        for nombre in ("persons", "users"):
            tabla = Base.metadata.tables[nombre]
            clave = "id_person" if nombre == "persons" else "id_user"
            for fila in volcado["identidad"][nombre]:
                valores = {k: _deserializar(v) for k, v in fila.items()}
                ya_esta = conexion.execute(
                    select(tabla.c[clave]).where(tabla.c[clave] == valores[clave])
                ).first()
                if not ya_esta:
                    conexion.execute(insert(tabla).values(**valores))
                    recreadas += 1

        # El plan, por nombre. Es lo único que se remapea.
        plans = Base.metadata.tables["plans"]
        plan_id = conexion.execute(
            select(plans.c.id).where(plans.c.nombre == volcado["plan"])
        ).scalar()
        if plan_id is None:
            plan_id = conexion.execute(
                insert(plans).values(nombre=volcado["plan"], precio_mensual=0)
            ).inserted_primary_key[0]

        insertadas = {}
        for nombre in TABLAS_DE_COMPANIA:
            filas = [
                {k: _deserializar(v) for k, v in fila.items()}
                for fila in volcado["tablas"][nombre]
            ]
            if not filas:
                continue
            if nombre == "companies":
                for fila in filas:
                    fila["plan_id"] = plan_id
            conexion.execute(insert(Base.metadata.tables[nombre]), filas)
            insertadas[nombre] = len(filas)

    print(f"Restaurada afiliado {volcado['afiliado']} · compañía {volcado['compania']} — "
          f"{volcado['nombre']}")
    for nombre, cuantas in insertadas.items():
        print(f"             {nombre:22} {cuantas}")
    if recreadas:
        print(f"Identidad  {recreadas} filas recreadas (ya no existían)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="orden", required=True)

    e = sub.add_parser("exportar", help="vuelca una compañía a un archivo")
    e.add_argument("--afiliado", type=int, required=True)
    e.add_argument("--compania", type=int, required=True)
    e.add_argument("--salida", required=True)

    b = sub.add_parser("borrar", help="borra las filas de una compañía")
    b.add_argument("--afiliado", type=int, required=True)
    b.add_argument("--compania", type=int, required=True)
    b.add_argument("--confirmar", required=True, help="el par afiliado-compania, p. ej. 2-1")

    i = sub.add_parser("importar", help="restaura una compañía desde un archivo")
    i.add_argument("--entrada", required=True)

    args = ap.parse_args()
    try:
        if args.orden == "exportar":
            exportar(args.afiliado, args.compania, args.salida)
        elif args.orden == "borrar":
            borrar(args.afiliado, args.compania, args.confirmar)
        else:
            importar(args.entrada)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"\nNo se pudo completar: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
