"""El modelo y las migraciones dicen lo mismo (T-915).

Una instalación **nueva** arma el esquema con `create_all` a partir de los
modelos; una **vieja** lo trae de `migrations/*.sql`. Si los dos no declaran los
mismos índices y las mismas restricciones, el mismo código corre sobre dos bases
distintas —y la diferencia no se ve hasta que muerde—.

Ya mordió dos veces. En F3, `audit_log` tenía sus índices solo en la migración,
así que la base de pruebas —hecha con `create_all`— no los tenía. Y al escribir
esta prueba aparecieron **cuatro UNIQUE** que ningún modelo declaraba:

    companies      (afiliado, compania)      la identidad del cliente
    branches       (company_id, codigo)      el código del consecutivo
    terminals      (company_id, branch_id, codigo)
    user_companies (user_id, company_id)     la membresía duplicada

Esa última es la que explica por qué esto va como prueba. `docker-compose.test.yml`
no corre las migraciones: crea la base con `create_all`. O sea que **toda la
batería corría sobre un esquema que aceptaba membresías duplicadas** mientras la
base de producción las rechazaba. Un camino de código que las creara pasaba en
verde acá y reventaba con `IntegrityError` en la base del cliente.

Se lee el SQL y no se levanta ninguna base: la prueba corre sin Docker, igual que
`test_layers.py`.
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

#: En orden de aplicación. El orden importa porque una migración posterior puede
#: quitar un índice que puso una anterior (la 005 reemplaza el UNIQUE de
#: `categories`).
#:
#: **`migration.sql` NO va acá, y costó verlo.** No es el esquema base: son
#: «arreglos heredados, para una base anterior a F1» (backend/README.md:23) y
#: **nunca se aplicó a esta base**. Se comprobó mirando los nombres de los
#: índices vivos: `products` tiene `ix_products_barcode` —el nombre que genera
#: SQLAlchemy— y no `idx_products_barcode`, que es el que declara ese archivo. O
#: sea que las tablas base las creó `create_all` al arrancar y encima se
#: corrieron las migraciones numeradas.
#:
#: Incluirlo hacía que esta prueba comparara contra un esquema que **nadie
#: tiene**, y de ahí salieron nueve índices que parecían faltarle al modelo y en
#: realidad no existen en ninguna base. Los que valían la pena se agregaron a la
#: 006, que es lo que sí los pone en producción.
MIGRACIONES = [
    "migrations/002-multiempresa.sql",
    "migrations/003-invitaciones.sql",
    "migrations/004-soporte.sql",
    "migrations/005-categorias.sql",
    "migrations/006-impuesto-por-producto.sql",
    "migrations/007-sin-defecto-de-compania.sql",
    "migrations/008-modulos-por-plan.sql",
    "migrations/009-compras.sql",
    "migrations/010-contabilidad.sql",
]

#: `persons` es la única tabla que nace solo de `create_all`, en los dos caminos:
#: no está en `migration.sql` ni en ninguna migración. Es identidad, como `users`,
#: y ninguna migración la ha necesitado. Se declara acá para que aparecer en esta
#: lista sea una decisión y no un descuido.
SIN_MIGRACION = {"persons"}

#: Los índices que crea `create_all` a partir de un `index=True` y que ninguna
#: migración declara. **No son un descuido: están en las bases desplegadas.**
#:
#: Las tablas de negocio nacieron de `create_all` —no de un `.sql`— y ahí
#: SQLAlchemy les creó estos índices con su nombre `ix_<tabla>_<columna>`. Los
#: catorce son redundantes: trece duplican `PRIMARY` y `ix_products_barcode`
#: duplica el prefijo izquierdo de `uq_products_company_barcode`. Quitarlos del
#: modelo dejaría a una instalación nueva sin ellos mientras las que ya corren
#: los tienen, o sea la divergencia que esta prueba existe para impedir;
#: igualarlos por el otro lado sería un DROP INDEX en producción, y se decidió
#: no hacerlo (T-915, 2026-09-05).
#:
#: Las seis tablas de `model_company.py` NO están acá y no pueden estar: las creó
#: la migración 002/004, así que `create_all` nunca las tocó y nunca tuvieron
#: este índice. Por eso sus claves primarias no llevan `index=True`.
#:
#: Una entrada nueva en esta lista tiene que venir con la misma comprobación:
#: que el índice exista de verdad en una base desplegada.
INDICES_DE_CREATE_ALL = {
    ("cash_movements", "ix_cash_movements_id"),
    ("cash_sessions", "ix_cash_sessions_id"),
    ("categories", "ix_categories_id"),
    ("clients", "ix_clients_id_client"),
    ("persons", "ix_persons_id_person"),
    ("products", "ix_products_barcode"),
    ("products", "ix_products_id_product"),
    ("return_details", "ix_return_details_id"),
    ("returns", "ix_returns_id"),
    ("sale_details", "ix_sale_details_id"),
    ("sales", "ix_sales_id"),
    ("stock_entries", "ix_stock_entries_id"),
    ("stock_entry_details", "ix_stock_entry_details_id"),
    ("users", "ix_users_id_user"),
}

#: Índices que declara la migración con nombre. Se comparan por nombre porque el
#: nombre es lo que se lee en un `EXPLAIN` y en `information_schema`.
_DEFINICION = re.compile(r"\b(?:(UNIQUE)\s+)?(?:KEY|INDEX)\s+`?(\w+)`?\s*\(([^)]*)\)", re.I)
_ADD = re.compile(r"\bADD\s+(?:(UNIQUE)\s+)?(?:KEY|INDEX)\s+`?(\w+)`?\s*\(([^)]*)\)", re.I)
_DROP = re.compile(r"\bDROP\s+(?:INDEX|KEY)\s+`?(\w+)`?", re.I)
_CREATE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?\s*\((.*)\)", re.I | re.S
)
_ALTER = re.compile(r"ALTER\s+TABLE\s+`?(\w+)`?\s+(.*)", re.I | re.S)

#: La tercera forma de declarar un índice, y la que se escapó la primera vez:
#: `CREATE INDEX x ON tabla (cols)` suelto, fuera de todo CREATE TABLE y de todo
#: ALTER. La migración 006 la usa. Que faltara lo cazó la propia prueba, que es
#: para lo que está.
_CREATE_INDEX = re.compile(
    r"CREATE\s+(UNIQUE\s+)?INDEX\s+`?(\w+)`?\s+ON\s+`?(\w+)`?\s*\(([^)]*)\)", re.I | re.S
)
_DROP_INDEX_SUELTO = re.compile(r"DROP\s+INDEX\s+`?(\w+)`?\s+ON\s+`?(\w+)`?", re.I)

# ---------------------------------------------------------------- columnas
#
# La otra mitad del esquema (T-919). El defecto 19 fue justo de columnas —cinco
# con un tipo en el modelo y otro en la migración— y se había comprobado a mano
# una vez, en F2. Al escribir T-507 volvió a asomar por la puerta de al lado:
# `default="Unid"` es del lado de Python y **no emite `DEFAULT` en el DDL**, así
# que `create_all` habría creado la columna sin valor por omisión mientras la
# migración sí se lo pone. Lo cazó mirarlo a mano, que es lo que no escala.

#: Lo que aparece en el cuerpo de un `CREATE TABLE` y **no** es una columna.
_NO_ES_COLUMNA = re.compile(
    r"^\s*(PRIMARY\s+KEY|UNIQUE\s+KEY|UNIQUE\s+INDEX|UNIQUE\b|KEY\b|INDEX\b"
    r"|CONSTRAINT\b|FOREIGN\s+KEY|CHECK\b)",
    re.I,
)

#: `ADD COLUMN x …` y también `ADD x …`, que MySQL acepta. Se corta en la coma
#: que abre la siguiente cláusula y no en cualquiera: un `DECIMAL(10,2)` trae la
#: suya adentro.
_ADD_COLUMNA = re.compile(
    r"\bADD\s+(?:COLUMN\s+)?`?(\w+)`?\s+(.*?)"
    r"(?=,\s*(?:ADD|DROP|MODIFY|CHANGE|CONSTRAINT)\b|$)",
    re.I | re.S,
)
_DROP_COLUMNA = re.compile(r"\bDROP\s+COLUMN\s+`?(\w+)`?", re.I)

#: Cambiar **solo** el valor por omisión, sin repetir el tipo. Es lo que hace la
#: 007 dieciocho veces, y sin leerlo esta prueba seguiría viendo el defecto que
#: esa migración quitó.
_ALTER_DEFECTO = re.compile(
    r"\bALTER\s+(?:COLUMN\s+)?`?(\w+)`?\s+"
    r"(?:(DROP)\s+DEFAULT|SET\s+DEFAULT\s+('(?:[^']|'')*'|[^\s,]+))",
    re.I,
)

#: Palabras que `_ADD_COLUMNA` capturaría como nombre de columna y no lo son.
_NO_ES_NOMBRE = {"UNIQUE", "KEY", "INDEX", "CONSTRAINT", "PRIMARY", "COLUMN", "FOREIGN"}

#: Columnas cuyo valor por omisión difiere **a propósito** entre las dos formas.
#:
#: **Está vacía, y esa es la idea.** Se deja declarada porque la lista de índices
#: de arriba enseñó que la excepción llega tarde o temprano y conviene que tenga
#: un sitio con su regla escrita: una entrada acá tiene que decir por qué la
#: diferencia es correcta y por qué no se puede cerrar por ninguno de los dos
#: lados.
#:
#: Hubo dieciocho hasta la 007 —el `DEFAULT 1` de `company_id`, `branch_id` y
#: `terminal_id`, cicatriz del backfill de la 002— y no entraron acá: se
#: quitaron de la base, que es lo que de verdad cierra la divergencia.
OMISIONES_DE_LA_MIGRACION: set[tuple[str, str]] = set()

#: El mismo tipo escrito de dos maneras. La izquierda es como lo compila
#: SQLAlchemy para MySQL; la derecha, como lo escribe una migración a mano.
_SINONIMOS = {
    "INTEGER": "INT",
    "NUMERIC": "DECIMAL",
    "BOOL": "TINYINT(1)",
    "BOOLEAN": "TINYINT(1)",
}


def _sin_comentarios(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def _por_comas_de_primer_nivel(cuerpo: str) -> list[str]:
    """Corta por comas, saltando las que van dentro de paréntesis.

    `precio DECIMAL(10,2) NOT NULL` es **una** parte, no dos.
    """
    partes: list[str] = []
    nivel = 0
    actual: list[str] = []
    for caracter in cuerpo:
        if caracter == "(":
            nivel += 1
        elif caracter == ")":
            nivel -= 1
        if caracter == "," and nivel == 0:
            partes.append("".join(actual))
            actual = []
        else:
            actual.append(caracter)
    if "".join(actual).strip():
        partes.append("".join(actual))
    return partes


def _forma_de_la_columna(definicion: str) -> tuple[str, bool, str | None, str | None]:
    """`(tipo, admite nulos, valor por omisión, expresión generada)`.

    Se compara la **forma** y no el texto: las dos fuentes dicen lo mismo con
    palabras distintas —`INT` contra `INTEGER`, `TINYINT(1)` contra `BOOL`,
    `DECIMAL(7,6)` contra `NUMERIC(7, 6)`— y una columna sin `NOT NULL` admite
    nulos aunque no lo escriba.

    Lo que se descarta es lo que no cambia qué acepta la base: `AFTER x` es
    posición, y `COMMENT`, `CHARACTER SET` y `COLLATE` no los declara el modelo.
    """
    texto = " ".join(definicion.split())
    for sobra in (
        r"\bAFTER\s+`?\w+`?",
        r"\bCOMMENT\s+'(?:[^']|'')*'",
        r"\bCHARACTER\s+SET\s+\w+",
        r"\bCOLLATE\s+\w+",
        # La PRIMARY KEY se compara aparte, y las dos fuentes la escriben en
        # sitios distintos: la migración pegada a la columna, SQLAlchemy en una
        # línea propia al final del CREATE TABLE.
        r"\bPRIMARY\s+KEY\b",
        # `AS (…) STORED` y `GENERATED ALWAYS AS (…) STORED` son lo mismo.
        r"\bGENERATED\s+ALWAYS\s+",
    ):
        texto = re.sub(sobra, " ", texto, flags=re.I)

    generada = None
    calculada = re.search(r"\bAS\s*\((.*)\)\s*(?:STORED|VIRTUAL)?", texto, re.I | re.S)
    if calculada:
        generada = re.sub(r"\s+", "", calculada.group(1)).upper()
        texto = texto[: calculada.start()] + " " + texto[calculada.end() :]

    # En MySQL una columna AUTO_INCREMENT es NOT NULL aunque no lo diga.
    automatica = bool(re.search(r"\bAUTO_INCREMENT\b", texto, re.I))
    texto = re.sub(r"\bAUTO_INCREMENT\b", " ", texto, flags=re.I)

    omision = None
    porOmision = re.search(r"\bDEFAULT\s+('(?:[^']|'')*'|[^\s,]+)", texto, re.I)
    if porOmision:
        omision = porOmision.group(1).upper()
        texto = texto[: porOmision.start()] + " " + texto[porOmision.end() :]

    no_nulo = automatica or bool(re.search(r"\bNOT\s+NULL\b", texto, re.I))
    texto = re.sub(r"\bNOT\s+NULL\b|\bNULL\b", " ", texto, flags=re.I)

    tipo = " ".join(texto.split()).upper()
    tipo = re.sub(r"\s*([(),])\s*", r"\1", tipo)
    base = re.match(r"[A-Z_]+", tipo)
    if base and base.group(0) in _SINONIMOS:
        equivalente = _SINONIMOS[base.group(0)]
        resto = tipo[base.end() :]
        # `BOOL` ya trae su longitud en el sinónimo; `INTEGER(11)` conserva la suya.
        tipo = equivalente if equivalente.endswith(")") else equivalente + resto
    return (tipo, not no_nulo, omision, generada)


def _columnas_del_cuerpo(cuerpo: str) -> dict[str, tuple]:
    """Las columnas de un `CREATE TABLE`, ya normalizadas."""
    encontradas: dict[str, tuple] = {}
    for parte in _por_comas_de_primer_nivel(cuerpo):
        if _NO_ES_COLUMNA.match(parte):
            continue
        declaracion = re.match(r"\s*`?(\w+)`?\s+(.*)", parte, re.S)
        if declaracion:
            encontradas[declaracion.group(1)] = _forma_de_la_columna(declaracion.group(2))
    return encontradas


def _columnas(texto: str) -> tuple[str, ...]:
    salida = []
    for parte in texto.split(","):
        parte = parte.strip().strip("`").strip()
        parte = re.sub(r"\(\d+\)$", "", parte)  # `col(20)`, prefijo de longitud
        if parte:
            salida.append(parte)
    return tuple(salida)


@dataclass
class Esquema:
    """Lo que declaran las migraciones, en un solo recorrido.

    Va junto y no en dos funciones porque las tres cosas se leen de las mismas
    sentencias y en el mismo orden, y ese orden es la parte delicada: una
    migración posterior puede quitar lo que puso una anterior.
    """

    #: `{tabla: {nombre: (columnas, único)}}`
    indices: dict[str, dict[str, tuple]]
    #: `{tabla: {columna: (tipo, admite nulos, valor por omisión, generada)}}`
    columnas: dict[str, dict[str, tuple]]
    #: Las tablas que una migración **crea**, no solo altera. La distinción
    #: importa: de esas se conoce el juego completo de columnas, así que se
    #: pueden comparar en los dos sentidos. De las demás la migración solo
    #: agrega, y las columnas originales las creó `create_all`.
    creadas: set[str]


def leer_migraciones() -> Esquema:
    """Recorre los `.sql` en orden y devuelve lo que declaran."""
    indices: dict[str, dict[str, tuple]] = {}
    columnas: dict[str, dict[str, tuple]] = {}
    creadas: set[str] = set()

    for relativa in MIGRACIONES:
        sql = _sin_comentarios((RAIZ / relativa).read_text(encoding="utf-8"))
        for sentencia in sql.split(";"):
            sentencia = sentencia.strip()
            if not sentencia:
                continue
            suelto = _CREATE_INDEX.match(sentencia)
            if suelto:
                unico, nombre, tabla, cols = suelto.groups()
                indices.setdefault(tabla, {})[nombre] = (_columnas(cols), bool(unico))
                continue

            quitado = _DROP_INDEX_SUELTO.match(sentencia)
            if quitado:
                nombre, tabla = quitado.groups()
                indices.setdefault(tabla, {}).pop(nombre, None)
                continue

            creacion = _CREATE.match(sentencia)
            if creacion:
                tabla, cuerpo = creacion.group(1), creacion.group(2)
                creadas.add(tabla)
                declarados = indices.setdefault(tabla, {})
                for unico, nombre, cols in _DEFINICION.findall(cuerpo):
                    declarados[nombre] = (_columnas(cols), bool(unico))
                columnas.setdefault(tabla, {}).update(_columnas_del_cuerpo(cuerpo))
                continue

            alteracion = _ALTER.match(sentencia)
            if alteracion:
                tabla, resto = alteracion.group(1), alteracion.group(2)
                declarados = indices.setdefault(tabla, {})
                for unico, nombre, cols in _ADD.findall(resto):
                    declarados[nombre] = (_columnas(cols), bool(unico))
                for nombre in _DROP.findall(resto):
                    declarados.pop(nombre, None)

                de_la_tabla = columnas.setdefault(tabla, {})
                for nombre, definicion in _ADD_COLUMNA.findall(resto):
                    if nombre.upper() in _NO_ES_NOMBRE:
                        continue
                    de_la_tabla[nombre] = _forma_de_la_columna(definicion)
                for nombre in _DROP_COLUMNA.findall(resto):
                    de_la_tabla.pop(nombre, None)
                for nombre, quitado, puesto in _ALTER_DEFECTO.findall(resto):
                    if nombre not in de_la_tabla:
                        continue
                    tipo, nulos, _, generada = de_la_tabla[nombre]
                    de_la_tabla[nombre] = (
                        tipo,
                        nulos,
                        None if quitado else puesto.upper(),
                        generada,
                    )

    return Esquema(indices=indices, columnas=columnas, creadas=creadas)


def indices_de_las_migraciones() -> dict[str, dict[str, tuple]]:
    """`{tabla: {nombre: (columnas, único)}}` recorriendo los `.sql` en orden."""
    return leer_migraciones().indices


def _cargar_modelos() -> None:
    """Importa todos los modelos para que `Base.metadata` los conozca."""
    for modulo in sorted((RAIZ / "app" / "models").glob("*.py")):
        if modulo.stem != "__init__":
            importlib.import_module(f"app.models.{modulo.stem}")


def indices_del_modelo() -> dict[str, dict[str, tuple]]:
    """Lo mismo, leído de `Base.metadata`."""
    from sqlalchemy import UniqueConstraint

    from app.database.database import Base

    _cargar_modelos()

    salida: dict[str, dict[str, tuple]] = {}
    for nombre_tabla, tabla in Base.metadata.tables.items():
        declarados: dict[str, tuple] = {}
        for indice in tabla.indexes:
            declarados[indice.name] = (
                tuple(c.name for c in indice.columns),
                bool(indice.unique),
            )
        for restriccion in tabla.constraints:
            if isinstance(restriccion, UniqueConstraint) and restriccion.name:
                declarados[restriccion.name] = (
                    tuple(c.name for c in restriccion.columns),
                    True,
                )
        salida[nombre_tabla] = declarados
    return salida


def columnas_del_modelo() -> dict[str, dict[str, tuple]]:
    """Lo mismo, leído del DDL que **emitiría `create_all`**.

    No se traduce el tipo de SQLAlchemy a mano: se le pide a SQLAlchemy que
    compile el `CREATE TABLE` para MySQL y se lee eso con el mismo lector que
    los `.sql`. Así lo comparado es literalmente lo que corre una instalación
    nueva contra lo que corrió una vieja, y no la opinión de esta prueba sobre
    a qué equivale un `Numeric(7, 6)`.

    Es además lo que hace visible el caso de T-507: un `default=` de Python no
    aparece en este DDL, y un `server_default=` sí.
    """
    from sqlalchemy.dialects import mysql
    from sqlalchemy.schema import CreateTable

    from app.database.database import Base

    _cargar_modelos()

    salida: dict[str, dict[str, tuple]] = {}
    for nombre_tabla, tabla in Base.metadata.tables.items():
        ddl = str(CreateTable(tabla).compile(dialect=mysql.dialect()))
        cuerpo = ddl[ddl.index("(") + 1 : ddl.rindex(")")]
        salida[nombre_tabla] = _columnas_del_cuerpo(cuerpo)
    return salida


@pytest.fixture(scope="module")
def esquema() -> Esquema:
    return leer_migraciones()


@pytest.fixture(scope="module")
def migracion() -> dict[str, dict[str, tuple]]:
    return indices_de_las_migraciones()


@pytest.fixture(scope="module")
def modelo() -> dict[str, dict[str, tuple]]:
    return indices_del_modelo()


@pytest.fixture(scope="module")
def columnas() -> dict[str, dict[str, tuple]]:
    return columnas_del_modelo()


def test_el_lector_de_sql_encuentra_algo(migracion):
    """La prueba de la prueba.

    Todo lo de abajo compara dos conjuntos, y un lector roto devuelve el conjunto
    vacío: las comparaciones pasarían en verde sin haber mirado nada. Es el
    defecto 25 del proyecto —una búsqueda invertida que daba cero y se creyó—, y
    la lección fue que un cero se comprueba al revés antes de creerle.

    Se fijan tres cosas que se sabe que están, una por forma de declararlas:
    dentro del `CREATE TABLE`, por `ALTER … ADD`, y una que una migración
    posterior **quitó**.
    """
    assert migracion["companies"]["uq_companies_afiliado_compania"] == (
        ("afiliado", "compania"),
        True,
    ), "no leyó un UNIQUE declarado dentro del CREATE TABLE"
    assert migracion["products"]["uq_products_company_barcode"] == (
        ("company_id", "barcode"),
        True,
    ), "no leyó un UNIQUE agregado por ALTER"
    assert "uq_categories_company_name" not in migracion["categories"], (
        "no aplicó un DROP INDEX: la 005 reemplazó ese UNIQUE y el lector lo "
        "sigue viendo, así que está leyendo las migraciones fuera de orden"
    )
    assert migracion["products"]["idx_products_cabys"] == (
        ("company_id", "cabys_code"),
        False,
    ), "no leyó un CREATE INDEX suelto, fuera de un CREATE TABLE y de un ALTER"
    assert len(migracion) >= 14


def test_toda_tabla_de_la_migracion_existe_en_el_modelo(migracion, modelo):
    faltan = sorted(set(migracion) - set(modelo))
    assert not faltan, f"tablas creadas por migración y sin modelo: {faltan}"


def test_solo_persons_nace_sin_migracion(migracion, modelo):
    """Una tabla que solo existe en el modelo la crea `create_all` y nadie más.

    No es un error por sí mismo —así nació `persons`— pero tiene que ser una
    decisión: una tabla nueva que aparezca acá sin estar en `SIN_MIGRACION`
    significa que se agregó al modelo y se olvidó la migración, y las
    instalaciones ya desplegadas no la van a tener.
    """
    solo_modelo = set(modelo) - set(migracion) - SIN_MIGRACION
    assert not solo_modelo, (
        f"tablas en el modelo y en ninguna migración: {sorted(solo_modelo)}. "
        "Si es a propósito, agregalas a SIN_MIGRACION con su porqué."
    )


def test_todo_indice_de_la_migracion_esta_en_el_modelo(migracion, modelo):
    """El caso peligroso: la base desplegada tiene algo que el modelo no declara.

    Es de este lado que estaban las cuatro UNIQUE, y es el que cambia lo que la
    base acepta —no solo lo que tarda—.
    """
    faltan = {
        tabla: sorted(set(declarados) - set(modelo.get(tabla, {})))
        for tabla, declarados in migracion.items()
        if set(declarados) - set(modelo.get(tabla, {}))
    }
    assert not faltan, (
        f"la migración los declara y el modelo no: {faltan}. Una instalación "
        "nueva no los tendría."
    )


def test_todo_indice_del_modelo_esta_en_la_migracion(migracion, modelo):
    """El caso al revés: una instalación nueva tiene algo que la desplegada no.

    Menos grave y igual de prohibido. Acá estaban los `ix_<tabla>_company_id` que
    creaba `index=True` del `TenantMixin` —duplicados del índice que InnoDB ya
    fabrica para la foránea— y los `ix_<tabla>_<pk>`, duplicados de `PRIMARY`.
    """
    sobran = {}
    for tabla, declarados in modelo.items():
        if tabla in SIN_MIGRACION:
            continue
        extra = {
            nombre
            for nombre in set(declarados) - set(migracion.get(tabla, {}))
            if (tabla, nombre) not in INDICES_DE_CREATE_ALL
        }
        if extra:
            sobran[tabla] = sorted(extra)
    assert not sobran, (
        f"el modelo los declara y la migración no: {sobran}. Una instalación "
        "migrada no los tendría."
    )


def test_ninguna_excepcion_es_de_adorno(modelo):
    """Una lista de excepciones que no corresponde a nada tranquiliza sin cubrir.

    Si alguien quita un `index=True` y se olvida de esta lista, la entrada queda
    permitiendo un índice que ya no existe —y el día que vuelva a aparecer, por
    otra razón, entraría sin que nadie lo mirara—.
    """
    huerfanas = sorted(
        f"{tabla}.{nombre}"
        for tabla, nombre in INDICES_DE_CREATE_ALL
        if nombre not in modelo.get(tabla, {})
    )
    assert not huerfanas, (
        f"están en INDICES_DE_CREATE_ALL y el modelo no los declara: {huerfanas}. "
        "O se quitó el `index=True` y hay que sacarlos de la lista, o se escribió "
        "mal el nombre."
    )


def test_los_indices_con_el_mismo_nombre_dicen_lo_mismo(migracion, modelo):
    """Mismo nombre y distinto contenido es peor que faltar: no se nota.

    Un índice al que se le cambió el orden de las columnas deja de servir para la
    consulta que lo justificaba, y sigue llamándose igual.
    """
    distintos = {}
    for tabla, declarados in migracion.items():
        del_modelo = modelo.get(tabla, {})
        for nombre, forma in declarados.items():
            if nombre in del_modelo and del_modelo[nombre] != forma:
                distintos[f"{tabla}.{nombre}"] = {
                    "migración": forma,
                    "modelo": del_modelo[nombre],
                }
    assert not distintos, f"mismo nombre, distinto contenido: {distintos}"


# ---------------------------------------------------------------------------
# Columnas (T-919)
#
# Lo de arriba compara índices y restricciones: lo que la base **acepta** y lo
# que **tarda**. Falta lo que la base **guarda**, que es donde estuvo el defecto
# 19 —cinco columnas con un tipo en el modelo y otro en la migración— y donde
# volvió a asomar en T-507 con un valor por omisión que solo existía de un lado.
# ---------------------------------------------------------------------------


def test_el_lector_de_columnas_encuentra_algo(esquema):
    """La prueba de la prueba, otra vez.

    Un lector de columnas roto devuelve diccionarios vacíos y todas las
    comparaciones de abajo pasan sin haber mirado nada. Se fija una columna por
    cada forma de declararla, y una de cada cosa que hay que normalizar.
    """
    assert esquema.columnas["companies"]["estado"] == ("VARCHAR(20)", False, "'PRUEBA'", None), (
        "no leyó una columna declarada dentro del CREATE TABLE, con su omisión"
    )
    assert esquema.columnas["products"]["tax_rate"] == ("DECIMAL(7,6)", True, None, None), (
        "no leyó una columna agregada por ALTER … ADD COLUMN"
    )
    assert esquema.columnas["products"]["unit_of_measure"] == (
        "VARCHAR(15)",
        False,
        "'UNID'",
        None,
    ), "no leyó el valor por omisión de una columna agregada por ALTER"
    assert esquema.columnas["categories"]["parent_key"] == (
        "INT",
        False,
        None,
        "IFNULL(PARENT_ID,0)",
    ), "no leyó una columna generada"
    assert esquema.columnas["users"]["is_support"] == ("TINYINT(1)", False, "0", None)

    # Y que sepa cuáles tablas **crea** una migración: de esas se conoce el juego
    # completo de columnas y por eso se comparan en los dos sentidos.
    assert "companies" in esquema.creadas
    assert "products" not in esquema.creadas, (
        "`products` la crea `create_all`; las migraciones solo le agregan columnas"
    )
    assert len(esquema.columnas) >= 18


def test_toda_columna_de_la_migracion_existe_en_el_modelo(esquema, columnas):
    """El caso peligroso: la base desplegada tiene una columna que el modelo no
    declara, así que una instalación nueva no la va a tener."""
    faltan = {
        tabla: sorted(set(declaradas) - set(columnas.get(tabla, {})))
        for tabla, declaradas in esquema.columnas.items()
        if set(declaradas) - set(columnas.get(tabla, {}))
    }
    assert not faltan, (
        f"la migración las declara y el modelo no: {faltan}. Una instalación "
        "nueva no las tendría."
    )


def test_toda_columna_del_modelo_esta_en_la_migracion_que_creo_su_tabla(esquema, columnas):
    """El caso al revés, y solo se puede exigir en las tablas que **crea** una
    migración: de las demás, la migración agrega columnas y las originales las
    puso `create_all`, así que su ausencia acá no dice nada."""
    sobran = {}
    for tabla in sorted(esquema.creadas):
        extra = sorted(set(columnas.get(tabla, {})) - set(esquema.columnas.get(tabla, {})))
        if extra:
            sobran[tabla] = extra
    assert not sobran, (
        f"el modelo las declara y la migración que creó la tabla no: {sobran}. "
        "Una instalación migrada no las tendría."
    )


def test_las_columnas_con_el_mismo_nombre_dicen_lo_mismo(esquema, columnas):
    """Tipo, nulabilidad, valor por omisión y expresión generada.

    Mismo nombre y distinta forma es lo que hace que el mismo código guarde
    cosas distintas según cómo se armó la base: un `DECIMAL(10,2)` de un lado y
    un `DECIMAL(7,6)` del otro redondean la tarifa a dos decimales en una
    instalación y no en la otra, sin que nada falle.
    """
    campos = ("tipo", "nulos", "omisión", "generada")
    distintas = {}
    for tabla, declaradas in esquema.columnas.items():
        del_modelo = columnas.get(tabla, {})
        for nombre, forma in declaradas.items():
            if nombre not in del_modelo or del_modelo[nombre] == forma:
                continue
            if (tabla, nombre) in OMISIONES_DE_LA_MIGRACION:
                continue
            distintas[f"{tabla}.{nombre}"] = {
                "difieren en": [c for c, a, b in zip(campos, forma, del_modelo[nombre]) if a != b],
                "migración": forma,
                "modelo": del_modelo[nombre],
            }
    assert not distintas, f"mismo nombre, distinta forma: {distintas}"


def test_ninguna_omision_declarada_es_de_adorno(esquema, columnas):
    """Igual que con los índices: una excepción que ya no corresponde a nada
    tranquiliza sin cubrir, y el día que la diferencia vuelva por otra razón
    entraría sin que nadie la mirara."""
    sin_diferencia = sorted(
        f"{tabla}.{nombre}"
        for tabla, nombre in OMISIONES_DE_LA_MIGRACION
        if esquema.columnas.get(tabla, {}).get(nombre) == columnas.get(tabla, {}).get(nombre)
        or nombre not in esquema.columnas.get(tabla, {})
    )
    assert not sin_diferencia, (
        f"están en OMISIONES_DE_LA_MIGRACION y ya no difieren —o la columna no "
        f"existe—: {sin_diferencia}. Sacalas de la lista."
    )
