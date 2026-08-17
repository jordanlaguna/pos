"""El filtro por compañía, probado directamente (T-206).

`test_aislamiento.py` comprueba el resultado —que por HTTP no se vea lo ajeno—.
Esto comprueba el mecanismo: que leer una tabla de negocio **sin compañía**
levante `SinCompania` en vez de devolver las filas de todo el mundo, que con
compañía devuelva solo las suyas, y que `sin_filtro()` sea la única salida.

Son cosas distintas y las dos hacen falta. Por HTTP no hay forma de llegar al
estado «sin compañía»: toda ruta de negocio pasa por la dependencia que la fija.
O sea que el caso que más importa —el que falla cerrado— es justamente el que la
batería de punta a punta no puede provocar.

**Sobre SQLite.** El proyecto no usa SQLite para las pruebas de caracterización,
y con razón: la venta toma `SELECT ... FOR UPDATE` y SQLite no lo entiende, así
que una prueba que pasara ahí no probaría lo que uno cree. Acá es distinto. Lo
que se prueba es un escuchador de SQLAlchemy que reescribe la consulta antes de
que llegue al motor; no depende del dialecto, y meter Docker y MySQL en el medio
solo agregaría formas de fallar ajenas a lo que se está comprobando. La prueba
corre en milisegundos y sin nada levantado, que es lo que uno quiere de la
prueba que protege el invariante más importante del sistema.
"""

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from app.database.database import Base

# Se importan **todos** los modelos aunque la prueba use tres. `create_all` arma
# las claves foráneas leyendo `Base.metadata`, y una tabla ausente no da una
# tabla de menos: hace fallar la creación entera con `NoReferencedTableError`
# —`user_companies.user_id` apunta a `users`—. Es la misma razón por la que
# `app/main.py` los importa todos antes de crear el esquema.
from app.models.model_cash import CashMovement, CashSession  # noqa: F401
from app.models.model_categories import Category
from app.models.model_client import Client  # noqa: F401
from app.models.model_company import AuditLog, Branch, Company, Plan, Terminal, UserCompany  # noqa: F401
from app.models.model_person import Person  # noqa: F401
from app.models.model_product import Product
from app.models.model_return import Return, ReturnDetail  # noqa: F401
from app.models.model_sale_details import SaleDetail  # noqa: F401
from app.models.model_sales import Sale  # noqa: F401
from app.models.model_settings import Settings  # noqa: F401
from app.models.model_stock_entry import StockEntry, StockEntryDetail  # noqa: F401
from app.models.model_user import User  # noqa: F401
from app.utils.tenancy import SinCompania, compania, current_company, sin_filtro

A = 1
B = 2


@pytest.fixture
def db():
    """Una base en memoria con dos compañías y un producto de cada una."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    sesion = Session()

    # La preparación crea filas de las dos compañías a propósito, así que dice
    # su `company_id` explícitamente: el sellado automático no pisa lo que ya
    # viene puesto, que es justo lo que permite escribir semillas.
    with compania(None):
        sesion.add(Plan(id=1, nombre="Comercio", precio_mensual=0))
        sesion.flush()
        for cid, nombre in ((A, "Compañía A"), (B, "Compañía B")):
            sesion.add(
                Company(
                    id=cid,
                    afiliado=cid,
                    compania=1,
                    nombre=nombre,
                    plan_id=1,
                    estado="activa",
                    creada_el=datetime(2026, 1, 1),
                )
            )
        sesion.flush()
        for cid, nombre in ((A, "Bebidas A"), (B, "Bebidas B")):
            sesion.add(Category(company_id=cid, name=nombre))
        sesion.flush()
        for cid, nombre in ((A, "Arroz de A"), (B, "Arroz de B")):
            sesion.add(
                Product(
                    company_id=cid,
                    name=nombre,
                    price=1000,
                    stock=10,
                    created_at=datetime(2026, 1, 1),
                    category_id=cid,
                )
            )
        sesion.commit()

    try:
        yield sesion
    finally:
        sesion.close()
        engine.dispose()


# ------------------------------------------------------------------- lectura


def test_sin_compania_no_devuelve_todo_sino_que_falla(db):
    """El corazón del asunto.

    La primera versión de este filtro decía «si hay compañía, filtrá». Con un
    usuario por compañía nunca se notaba, porque el `company_id` siempre venía en
    el token. La pantalla de selección crea el estado que faltaba —autenticado y
    todavía sin compañía— y en esa ventana la versión permisiva devuelve las
    filas de TODAS: sin error, sin aviso, en un reporte que se ve perfecto.
    """
    assert current_company.get() is None

    with pytest.raises(SinCompania):
        db.query(Product).all()


def test_con_compania_solo_se_ven_las_propias(db):
    with compania(A):
        nombres = [p.name for p in db.query(Product).all()]
    assert nombres == ["Arroz de A"]

    with compania(B):
        nombres = [p.name for p in db.query(Product).all()]
    assert nombres == ["Arroz de B"]


def test_sin_filtro_es_la_unica_salida_y_devuelve_las_de_todas(db):
    with compania(None):
        nombres = sorted(p.name for p in sin_filtro(db.query(Product)).all())
    assert nombres == ["Arroz de A", "Arroz de B"]

    # También cruza compañías cuando hay una fijada: es una decisión explícita
    # de quien escribe la consulta, no un descuido.
    with compania(A):
        assert sin_filtro(db.query(Product)).count() == 2


def test_el_filtro_alcanza_a_toda_tabla_de_negocio_no_solo_a_products(db):
    with compania(A):
        assert [c.name for c in db.query(Category).all()] == ["Bebidas A"]


def test_pedir_por_id_lo_ajeno_no_devuelve_nada(db):
    """De acá sale el 404 de la batería de aislamiento, y no de un `if` en la ruta."""
    with compania(B):
        ajeno = db.query(Product).one()

    with compania(A):
        assert db.query(Product).filter(Product.id_product == ajeno.id_product).first() is None


def test_las_tablas_que_no_son_de_negocio_se_leen_sin_compania(db):
    """`companies` y `plans` son raíz, no inquilinas.

    Si exigieran compañía, el login no podría averiguar a cuáles puede entrar
    alguien —que es la consulta que ocurre antes de que exista compañía—.
    """
    assert current_company.get() is None
    assert db.query(Company).count() == 2
    assert db.query(Plan).count() == 1


# ------------------------------------------------------------------ escritura


def test_una_fila_nueva_se_sella_con_la_compania_del_contexto(db):
    with compania(A):
        db.add(Product(name="Nuevo de A", price=500, stock=1, created_at=datetime(2026, 1, 2), category_id=1))
        db.commit()
        guardado = db.query(Product).filter(Product.name == "Nuevo de A").one()
        assert guardado.company_id == A


def test_guardar_sin_compania_falla_en_vez_de_quedar_huerfana(db):
    """La otra mitad del aislamiento.

    Si leer sin `WHERE` es imposible pero escribir sin `company_id` depende de
    que quince sitios se acuerden, el fallo entra por el lado de la escritura: la
    fila queda visible para nadie —o para quien tenga ese número— y el defecto
    aparece semanas después, con datos encima.
    """
    db.add(Product(name="Huérfano", price=500, stock=1, created_at=datetime(2026, 1, 2), category_id=1))
    with pytest.raises(SinCompania):
        db.commit()
    db.rollback()


def test_el_sellado_no_pisa_la_compania_que_ya_viene_puesta(db):
    """Es lo que permite que `bootstrap.py` y las semillas creen filas de otra."""
    with compania(A):
        db.add(
            Product(
                company_id=B,
                name="De B, creado desde el contexto de A",
                price=500,
                stock=1,
                created_at=datetime(2026, 1, 2),
                category_id=2,
            )
        )
        db.commit()

    # Se cuenta con `all()` y no con `count()` a propósito: ver la prueba
    # siguiente, donde se explica que `count()` no está cubierto por el filtro.
    with compania(B):
        assert len(db.query(Product).filter(Product.name.like("De B%")).all()) == 1
    with compania(A):
        assert db.query(Product).filter(Product.name.like("De B%")).all() == []


# ------------------------------------------------- el hueco, y su guardián


def test_count_no_esta_cubierto_por_el_filtro(db):
    """Un límite real de `with_loader_criteria`, escrito para que no sorprenda.

    `Query.count()` no ejecuta la consulta de la entidad: la envuelve en
    `SELECT count(*) FROM (…)`, y el criterio no entra en esa envoltura. O sea
    que `db.query(Product).count()` **cuenta las de todas las compañías**,
    mientras que `db.query(Product).all()` devuelve solo las propias.

    Es el mismo límite que plan §3.3 ya anotaba para el SQL agregado de los
    reportes, pero es mucho más peligroso acá: un `.count()` no parece SQL
    agregado, parece una llamada inocente del ORM.

    Esta prueba fija el comportamiento tal como es. Si algún día SQLAlchemy lo
    cubriera, se pondría roja y sería una buena noticia que hay que leer, no un
    fallo. El guardián de abajo es lo que impide que el hueco se use.
    """
    with compania(A):
        assert len(db.query(Product).all()) == 1, "el filtro sí cubre `all()`"
        assert db.query(Product).count() == 2, (
            "si esto ahora da 1, SQLAlchemy empezó a cubrir `count()`: "
            "actualizá plan §3.3 y quitá el guardián de la prueba siguiente"
        )

    # La forma que **sí** está cubierta, por si alguien necesita contar:
    with compania(A):
        assert db.query(func.count(Product.id_product)).scalar() == 1


def test_ningun_count_del_backend_puede_cruzar_companias():
    """El guardián: `.count()` solo se admite con su filtro a la vista.

    Como el filtro automático no cubre `count()`, la única defensa es que quien
    lo escriba ponga el `company_id` a mano. Eso no se puede dejar a la memoria:
    acá cualquier `.count()` sin `company_id` ni `sin_filtro` en la misma
    sentencia tumba `pytest`, que es la verificación que ya se corre al terminar.

    Se lee el árbol de sintaxis y no se importa nada, por la misma razón que
    `test_layers.py`: importar ejecuta código.
    """
    APP = Path(__file__).resolve().parent.parent / "app"
    culpables: list[str] = []

    for archivo in sorted(APP.rglob("*.py")):
        fuente = archivo.read_text(encoding="utf-8")
        if ".count()" not in fuente:
            continue
        arbol = ast.parse(fuente, filename=str(archivo))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.stmt):
                continue
            trozo = ast.get_source_segment(fuente, nodo) or ""
            if ".count()" not in trozo:
                continue
            # Solo la sentencia más interna que lo contiene, para no culpar a la
            # función entera por una línea de adentro.
            if any(
                isinstance(hijo, ast.stmt) and ".count()" in (ast.get_source_segment(fuente, hijo) or "")
                for hijo in ast.iter_child_nodes(nodo)
            ):
                continue
            if "company_id" in trozo or "sin_filtro" in trozo:
                continue
            culpables.append(f"{archivo.relative_to(APP.parent)}:{nodo.lineno}")

    assert not culpables, (
        "Estos `.count()` no llevan `company_id` a la vista, y el filtro "
        "automático no los cubre: cuentan las filas de TODAS las compañías.\n  "
        + "\n  ".join(culpables)
        + "\nUsá `db.query(func.count(Modelo.id))`, que sí se filtra, o escribí "
        "el `company_id` en la consulta."
    )


# -------------------------------------------------------------------- contexto


def test_el_contexto_se_restaura_aunque_el_bloque_lance(db):
    """Un `ContextVar` sucio hace fallar la prueba siguiente y no la que falla."""
    with pytest.raises(ValueError):
        with compania(A):
            raise ValueError("algo salió mal")
    assert current_company.get() is None


def test_los_contextos_se_anidan(db):
    with compania(A):
        with compania(B):
            assert [p.name for p in db.query(Product).all()] == ["Arroz de B"]
        assert [p.name for p in db.query(Product).all()] == ["Arroz de A"]
