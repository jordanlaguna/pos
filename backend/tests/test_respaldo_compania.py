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

from .conftest import API, BACKEND, Api, afiliado_unico, bootstrap, entrar, marca_unica

pytestmark = pytest.mark.characterization

#: Dentro del contenedor. `/tmp` es escribible por el usuario sin privilegios.
ARCHIVO = "/tmp/respaldo-compania-c.json"

CLAVE_C = "prueba123"


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
        "planilla": retrato_de_planilla(cliente),
    }


def retrato_de_planilla(cliente: Api) -> dict:
    """Las once tablas de la compañía de F12, vistas por la API (T-1201).

    La corrida pagada va con sus rubros: si uno solo no volviera, la boleta
    reimpresa después de restaurar diría otra cosa que la de antes (RN-66).
    """
    empleados = cliente.ok("GET", "/payroll/employees")
    corridas = cliente.ok("GET", "/payroll/runs")
    return {
        "jornadas": sorted((j["id"], j["name"], j["frequency"]) for j in cliente.ok("GET", "/payroll/schedules")),
        "puestos": sorted((p["id"], p["name"], p["ccss_code"]) for p in cliente.ok("GET", "/payroll/positions")),
        "polizas": sorted((p["id"], p["number"], p["rt_rate"]) for p in cliente.ok("GET", "/payroll/policies")),
        "empleados": sorted(
            (e["id"], e["identification"], e["contract"]["id"] if e["contract"] else None) for e in empleados
        ),
        "acciones": sorted(
            (a["id"], a["kind"], a["applied_total"])
            for e in empleados
            for a in cliente.ok("GET", f"/payroll/employees/{e['id']}/actions")
        ),
        "corridas": sorted((c["id"], c["status"], c["gross"], c["net"], c["employees"]) for c in corridas),
        "rubros": sorted(
            (c["id"], l["employee_id"], i["concept"], i["payer"], i["amount"], i["action_id"])
            for c in corridas
            for l in cliente.ok("GET", f"/payroll/runs/{c['id']}")["lines"]
            for i in l["items"]
        ),
    }


@pytest.fixture(scope="module")
def compania_c(api: Api) -> Api:
    """Una compañía propia de esta prueba, con datos suficientes para notar la pérdida.

    Con un afiliado distinto en cada corrida: la base de pruebas sobrevive entre
    corridas, y una compañía fija (la «3») nacía con el plan de su primera
    corrida —sin planilla— y no había forma de darle el módulo después.
    """
    marca = marca_unica()
    afiliado = afiliado_unico()
    correo = f"admin.c.{marca}@pruebas.ventasys.cr"
    bootstrap(
        afiliado=afiliado,
        compania=1,
        nombre="Compañía C, la que se restaura",
        email=correo,
        password=CLAVE_C,
        rol="admin",
        nombre_persona="Carla",
        apellido="Tercera",
        cedula=marca[-9:],
        plan=f"Plan C {marca}",
        plan_max_usuarios="-1",
        plan_modulos="payroll",
    )

    cliente = Api(API)
    sesion = entrar(cliente, correo, CLAVE_C)
    cliente.user_id = cliente.ok("GET", "/users/me")["id_user"]  # type: ignore[attr-defined]
    cliente.company_id = sesion["company_id"]  # type: ignore[attr-defined]
    cliente.afiliado = afiliado  # type: ignore[attr-defined]
    cliente.email = correo  # type: ignore[attr-defined]

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
            "identification_type": "01",
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

    # Planilla (T-1201): una corrida pagada con sus rubros y una acción
    # aplicada, que son las filas que más se enredan entre sí al restaurar.
    jornada = cliente.ok(
        "POST", "/payroll/schedules", {"name": "Quincenal", "frequency": "semimonthly", "first_cut_day": 15}
    )
    puesto = cliente.ok("POST", "/payroll/positions", {"name": "Cajera", "ccss_code": "4211", "ins_code": "52"})
    cliente.ok("POST", "/payroll/policies", {"number": "RT-C", "rt_rate": "0.0146"})
    empleada = cliente.ok(
        "POST",
        "/payroll/employees",
        {
            "identification_type": "national",
            "identification": marca[-9:],
            "first_name": "Carla",
            "last_name_1": "Tercera",
            "birth_date": "1990-05-20",
            "gender": "F",
            "marital_status": "single",
            "nationality": "CR",
            "hired_on": "2025-06-01",
        },
    )
    cliente.ok(
        "POST",
        "/payroll/contracts",
        {
            "employee_id": empleada["id"],
            "schedule_id": jornada["id"],
            "position_id": puesto["id"],
            "valid_from": "2025-06-01",
            "period_salary": "300000",
        },
    )
    cliente.ok(
        "POST",
        "/payroll/actions",
        {"employee_id": empleada["id"], "kind": "bonus", "starts_on": "2026-01-10", "amount": "5000"},
    )
    corrida = cliente.ok("POST", "/payroll/runs", {"schedule_id": jornada["id"], "cut_date": "2026-01-15"})
    cliente.ok("POST", f"/payroll/runs/{corrida['id']}/calculate")
    cliente.ok("POST", f"/payroll/runs/{corrida['id']}/approve")
    cliente.ok("POST", f"/payroll/runs/{corrida['id']}/pay")

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
        afiliado = str(compania_c.afiliado)  # type: ignore[attr-defined]
        salida = herramienta("exportar", "--afiliado", afiliado, "--compania", "1", "--salida", ARCHIVO)
        assert "sales" in salida and "products" in salida and "payroll_run_items" in salida

        # 2. Borrar. Sin la confirmación exacta no borra nada.
        fallo = subprocess.run(
            [
                "docker", "compose", "-f", "docker-compose.test.yml", "exec", "-T", "fastapi",
                "python", "company_dump.py", "borrar",
                "--afiliado", afiliado, "--compania", "1", "--confirmar", f"{afiliado}-2",
            ],
            cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        assert fallo.returncode != 0, "borró con una confirmación equivocada"

        herramienta("borrar", "--afiliado", afiliado, "--compania", "1", "--confirmar", f"{afiliado}-1")

        # 3. Con la compañía borrada, su administrador ya no tiene a dónde entrar.
        huerfano = Api(API)
        cuerpo = huerfano.ok(
            "POST", "/auth/login", {"email": compania_c.email, "password": CLAVE_C}  # type: ignore[attr-defined]
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
        entrar(de_nuevo, compania_c.email, CLAVE_C)  # type: ignore[attr-defined]
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
        afiliado = str(compania_c.afiliado)  # type: ignore[attr-defined]
        herramienta("exportar", "--afiliado", afiliado, "--compania", "1", "--salida", ARCHIVO)

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
    def test_ninguna_tabla_queda_fuera_del_respaldo_sin_decidirlo(self, compania_c: Api):
        """Si aparece una tabla nueva, la herramienta lo dice en vez de ignorarla.

        Una exportación incompleta es peor que ninguna: se descubre el día que
        hace falta restaurar, que es el peor día para descubrirlo.
        """
        afiliado = str(compania_c.afiliado)  # type: ignore[attr-defined]
        salida = herramienta("exportar", "--afiliado", afiliado, "--compania", "1", "--salida", ARCHIVO)
        assert "Compañía" in salida


class TestLoQueNoViajaEnElRespaldo:
    """La clasificación por COLUMNA, que es lo que F6 le enseñó al guardián.

    `fe_credentials` no se puede clasificar entera en un lado ni en el otro:
    adentro conviven lo que puede volver solo —el certificado público, el
    usuario de ATV, las fechas— y un secreto que no debe viajar. Afuera,
    restaurar deja al cliente sin saber qué le falta; adentro, el respaldo se
    lleva una contraseña (RN-47, T-601).
    """

    def test_la_contrasena_de_ATV_no_se_exporta(self):
        from company_dump import _columnas
        from app.database.database import Base

        columnas = {c.name for c in _columnas(Base.metadata.tables["fe_credentials"])}
        assert "atv_password_encrypted" not in columnas, (
            "la contraseña de ATV viaja en el respaldo. En otra instalación, con "
            "otra FE_CRYPTO_KEY, es un valor indescifrable que nadie distingue de "
            "uno bueno hasta el día de transmitir."
        )

    def test_pero_lo_que_puede_volver_solo_sí_viaja(self):
        # La otra mitad de la decisión, y la que hace que no se pueda clasificar
        # la tabla entera afuera: sin esto, restaurar deja a la compañía sin
        # saber siquiera qué ambiente tenía configurado.
        from company_dump import _columnas
        from app.database.database import Base

        columnas = {c.name for c in _columnas(Base.metadata.tables["fe_credentials"])}
        assert {
            "environment",
            "certificate_pem",
            "certificate_name",
            "expires_at",
            "atv_user",
            "key_custody",
        } <= columnas

    def test_el_p12_y_el_PIN_no_son_una_decisión_sino_una_imposibilidad(self):
        """No están en la base, así que el volcado no puede llevárselos.

        Es la diferencia entre una regla —que alguien puede cambiar sin
        pensarlo— y un hecho del esquema. Lo dio gratis llevar la llave privada
        a Vault (plan §7.1, 2026-09-13).
        """
        from app.database.database import Base

        todas = set(Base.metadata.tables["fe_credentials"].c.keys())
        assert not (todas & {"p12_encrypted", "pin_encrypted"}), (
            "volvió una columna para el .p12 o el PIN: con la llave en Vault no "
            "hay nada que guardar, y guardarlo sería tener dos copias de un "
            "secreto con una de ellas olvidable"
        )
