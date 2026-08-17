"""Respaldar, borrar y restaurar una compañía sin tocar a las demás (T-225).

Es la verificación que pedía T-217: **restaurar una compañía sin tocar una sola
fila de otra**. Sin esto, dar de baja a un cliente y devolverle sus datos es
trabajo manual sobre doce tablas, y volver atrás cuando una compañía se daña
significa restaurar el respaldo de toda la base —o sea, deshacerle el día a las
otras once que estaban vendiendo—.

La compañía que se destruye y se restaura es una **propia de esta prueba**
(afiliado 3), no la B que usan las demás. Da lo mismo para lo que se comprueba y
evita que un fallo a mitad de camino deje la pila de pruebas sin compañía B, con
media suite roja por un motivo que no es el suyo.

Corre contra la pila de `docker-compose.test.yml`, con el guion adentro del
contenedor: la base de la pila no publica puerto —vive en tmpfs— y además así se
ejecuta el mismo `company_dump.py` que se usaría de verdad.
"""

from __future__ import annotations

import subprocess

import pytest

from .conftest import API, BACKEND, Api, bootstrap, entrar, marca_unica

pytestmark = pytest.mark.characterization

#: Dentro del contenedor. `/tmp` es escribible por el usuario sin privilegios.
ARCHIVO = "/tmp/respaldo-compania-c.json"

ADMIN_C = {
    "email": "admin.c@pruebas.ventasys.cr",
    "password": "prueba123",
}


def herramienta(*argumentos: str) -> str:
    """Corre `company_dump.py` dentro del contenedor y devuelve su salida."""
    resultado = subprocess.run(
        [
            "docker", "compose", "-f", "docker-compose.test.yml",
            "exec", "-T", "fastapi", "python", "company_dump.py", *argumentos,
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        # UTF-8 explícito: en Windows, `subprocess` decodifica con la página de
        # códigos del sistema y el contenedor escribe UTF-8. Sin esto, «Compañía»
        # llega partida y cualquier comparación de texto falla por el motivo
        # equivocado.
        encoding="utf-8",
        timeout=180,
    )
    if resultado.returncode != 0:
        pytest.fail(
            f"company_dump.py {' '.join(argumentos)} falló:\n"
            f"{resultado.stdout}\n{resultado.stderr}"
        )
    return resultado.stdout


def retrato(cliente: Api) -> dict:
    """Todo lo que una compañía puede ver de sí misma, para comparar antes y después.

    Se toma por la API y no por SQL a propósito: lo que importa no es que las
    filas estén, sino que el negocio siga viendo lo mismo.
    """
    ventas = cliente.ok("GET", "/sales/sales_list")
    return {
        "productos": sorted(
            (p["id_product"], p["name"], float(p["price"]), p["stock"])
            for p in cliente.ok("GET", "/products/products_list")
        ),
        "clientes": sorted(
            (c["id_client"], c["identification"]) for c in cliente.ok("GET", "/clients/clients_list")
        ),
        "ventas": sorted((v["id"], v["sale_number"], float(v["total"])) for v in ventas),
        "total_vendido": round(sum(float(v["total"]) for v in ventas), 2),
        "categorias": sorted((c["id"], c["name"]) for c in cliente.ok("GET", "/categories/categories_list")),
        "entradas": sorted((e["id"], e["total_cost"]) for e in cliente.ok("GET", "/inventory/entries")),
        "devoluciones": sorted(
            (d["id"], float(d["total"])) for d in cliente.ok("GET", "/returns/returns_list")
        ),
        "configuracion": cliente.ok("GET", "/settings/")["data"],
    }


@pytest.fixture(scope="module")
def compania_c(api: Api) -> Api:
    """Una compañía propia de esta prueba, con datos suficientes para notar la pérdida."""
    bootstrap(
        afiliado=3,
        compania=1,
        nombre="Compañía C, la que se restaura",
        email=ADMIN_C["email"],
        password=ADMIN_C["password"],
        rol="admin",
        nombre_persona="Carla",
        apellido="Tercera",
        cedula="400000001",
    )

    cliente = Api(API)
    sesion = entrar(cliente, ADMIN_C["email"], ADMIN_C["password"])
    cliente.user_id = cliente.ok("GET", "/users/me")["id_user"]  # type: ignore[attr-defined]
    cliente.company_id = sesion["company_id"]  # type: ignore[attr-defined]

    marca = marca_unica()
    cliente.ok("POST", "/categories/register_category", {"name": f"Cat C {marca}"})
    categoria = next(
        c for c in cliente.ok("GET", "/categories/categories_list") if c["name"] == f"Cat C {marca}"
    )
    cliente.ok(
        "POST",
        "/products/add_product",
        {
            "name": f"Producto C {marca}",
            "description": "se va a borrar y a volver",
            "price": 2500,
            "stock": 30,
            "barcode": f"RESP{marca}",
            "created_at": "2026-01-01T00:00:00",
            "category_id": categoria["id"],
        },
    )
    producto = cliente.ok("GET", f"/products/product/RESP{marca}")

    cliente.ok(
        "POST",
        "/clients/register_client",
        {
            "identification": f"RC{marca}",
            "name": "Cliente",
            "last_name": "De C",
            "second_name": "Prueba",
            "email": f"cliente.{marca}@pruebas.cr",
            "telephone": 80000000,
            "address": "sin dirección",
            "register_date": "2026-01-01",
        },
    )

    for i in range(2):
        cliente.ok(
            "POST",
            "/sales/add_sale",
            {
                "sale_number": f"RESP{marca}{i}",
                "client_id": None,
                "user_id": cliente.user_id,  # type: ignore[attr-defined]
                "subtotal": 2500.0,
                "tax": 325.0,
                "total": 2825.0,
                "payment_method": "Efectivo",
                "cash_received": 3000.0,
                "change_given": 175.0,
                "products": [{"id_product": producto["id_product"], "stock": 1}],
            },
        )

    cliente.ok(
        "POST",
        "/inventory/entry",
        {
            "document_number": f"RESP{marca}",
            "supplier": "Proveedor de C",
            "source": "manual",
            "user_id": cliente.user_id,  # type: ignore[attr-defined]
            "notes": "para el respaldo",
            "lines": [{"id_product": producto["id_product"], "quantity": 7, "unit_cost": 1500}],
        },
    )

    # Configuración propia: es lo que delataría que se restauró la de otra.
    original = cliente.ok("GET", "/settings/")["data"] or {}
    cliente.ok(
        "PUT",
        "/settings/",
        {"data": {**original, "marca_de_c": f"C{marca}"}, "keep_logo": True},
    )

    return cliente


class TestRespaldoYRestauracion:
    def test_ida_y_vuelta_completa_sin_tocar_a_las_demas(self, api: Api, compania_c: Api):
        """La prueba entera, en un solo caso.

        Va junta a propósito: son pasos de un mismo procedimiento y partirlos en
        casos independientes obligaría a exportar y borrar varias veces, o a que
        un caso dependiera de que otro corriera antes —que es la clase de prueba
        que falla en un orden y pasa en otro—.
        """
        antes_de_a = retrato(api)
        antes_de_c = retrato(compania_c)
        assert antes_de_c["ventas"], "la compañía C tenía que tener ventas"

        # 1. Exportar.
        salida = herramienta("exportar", "--afiliado", "3", "--compania", "1", "--salida", ARCHIVO)
        assert "sales" in salida and "products" in salida

        # 2. Borrar. Sin la confirmación exacta no borra nada.
        fallo = subprocess.run(
            [
                "docker", "compose", "-f", "docker-compose.test.yml", "exec", "-T", "fastapi",
                "python", "company_dump.py", "borrar",
                "--afiliado", "3", "--compania", "1", "--confirmar", "3-2",
            ],
            cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        assert fallo.returncode != 0, "borró con una confirmación equivocada"

        herramienta("borrar", "--afiliado", "3", "--compania", "1", "--confirmar", "3-1")

        # 3. Con la compañía borrada, su administrador ya no tiene a dónde entrar.
        huerfano = Api(API)
        cuerpo = huerfano.ok(
            "POST", "/auth/login", {"email": ADMIN_C["email"], "password": ADMIN_C["password"]}
        )
        assert cuerpo["companies"] == [], (
            "la compañía se borró pero su administrador todavía la ve"
        )
        # La identidad sigue existiendo: por eso pudo autenticarse. Es lo
        # correcto —`users` es global y puede estar compartida— y además es lo
        # que permite que al restaurar las ventas sigan apuntando a alguien.
        assert cuerpo["user_id"]

        # 4. Y la compañía A no se enteró de nada.
        assert retrato(api) == antes_de_a, (
            "borrar la compañía C cambió algo de la A"
        )

        # 5. Restaurar.
        herramienta("importar", "--entrada", ARCHIVO)

        # 6. C volvió idéntica, con los mismos identificadores.
        de_nuevo = Api(API)
        entrar(de_nuevo, ADMIN_C["email"], ADMIN_C["password"])
        assert retrato(de_nuevo) == antes_de_c, (
            "la compañía restaurada no quedó igual que antes de borrarla"
        )

        # 7. Y A sigue sin enterarse.
        assert retrato(api) == antes_de_a, (
            "restaurar la compañía C cambió algo de la A"
        )

    def test_restaurar_encima_de_datos_existentes_se_niega(self, api: Api, compania_c: Api):
        """Falla cerrado.

        Es el precio de conservar los identificadores en vez de remapearlos, y es
        el comportamiento correcto: mezclar las filas viejas con las nuevas
        dejaría una compañía con dos versiones de su historia y ninguna forma de
        saber cuál es cuál.
        """
        herramienta("exportar", "--afiliado", "3", "--compania", "1", "--salida", ARCHIVO)

        resultado = subprocess.run(
            [
                "docker", "compose", "-f", "docker-compose.test.yml", "exec", "-T", "fastapi",
                "python", "company_dump.py", "importar", "--entrada", ARCHIVO,
            ],
            cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        assert resultado.returncode != 0, "restauró encima de una compañía con datos"
        assert "todavía tiene filas" in resultado.stdout + resultado.stderr


class TestCoberturaDelRespaldo:
    def test_ninguna_tabla_queda_fuera_del_respaldo_sin_decidirlo(self):
        """Si aparece una tabla nueva, la herramienta lo dice en vez de ignorarla.

        Una exportación incompleta es peor que ninguna: se descubre el día que
        hace falta restaurar, que es el peor día para descubrirlo.
        """
        salida = herramienta("exportar", "--afiliado", "3", "--compania", "1", "--salida", ARCHIVO)
        assert "Compañía" in salida
