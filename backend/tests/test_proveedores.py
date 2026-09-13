"""Proveedores (T-1007, RF-41, RN-49, RN-50).

Es la primera ruta que exige un módulo del plan, así que acá se comprueba de
verdad lo que `test_modulos.py` fija sobre la dependencia: que una escritura sin
el módulo rebote y que una lectura pase igual.
"""

from __future__ import annotations

import pytest

from tests.conftest import Api, bootstrap, codigo, entrar, marca_unica


def _nuevo(api: Api, **cambios) -> dict:
    marca = marca_unica()
    cuerpo = {
        "name": f"Mayorista {marca}",
        "identification_type": "02",
        "identification": f"3{marca}",
        "payment_terms_days": 30,
    }
    cuerpo.update(cambios)
    return api.ok("POST", "/suppliers", cuerpo)


class TestElAlta:
    def test_queda_activo_y_con_su_plazo(self, api: Api):
        proveedor = _nuevo(api, payment_terms_days=15)
        assert proveedor["is_active"] is True
        assert proveedor["payment_terms_days"] == 15
        assert proveedor["id"] > 0

    def test_sin_identificacion_tambien(self, api: Api):
        # El que trae la fruta el martes. Obligar la cédula haría que alguien la
        # invente, y una cédula inventada es peor que ninguna.
        proveedor = _nuevo(api, identification_type=None, identification=None)
        assert proveedor["identification"] is None

    def test_dos_sin_identificacion_conviven(self, api: Api):
        # El UNIQUE es (company_id, identification) y en MySQL dos NULL no chocan.
        primero = _nuevo(api, identification_type=None, identification=None)
        segundo = _nuevo(api, identification_type=None, identification=None)
        assert primero["id"] != segundo["id"]

    def test_la_misma_cedula_es_el_mismo_proveedor(self, api: Api):
        original = _nuevo(api)
        estado, cuerpo = api.call(
            "POST",
            "/suppliers",
            {"name": "Otro nombre", "identification": original["identification"]},
        )
        assert codigo((estado, cuerpo), 400) == "supplier_identification_taken"
        # Dice de quién es ya: sin el nombre hay que ir a buscarlo a la lista.
        assert cuerpo["detail"]["name"] == original["name"]

    def test_un_tipo_que_no_es_de_hacienda_no_pasa(self, api: Api):
        estado, cuerpo = api.call(
            "POST", "/suppliers", {"name": "X", "identification_type": "99", "identification": "1"}
        )
        assert codigo((estado, cuerpo), 400) == "invalid_identification_type"

    def test_un_tipo_sin_numero_no_pasa(self, api: Api):
        # Un «02» sin cédula jurídica es un dato a medias que después no sirve
        # ni para emitir ni para reconocerlo en un XML.
        estado, cuerpo = api.call(
            "POST", "/suppliers", {"name": "X", "identification_type": "02"}
        )
        assert codigo((estado, cuerpo), 400) == "identification_required"


class TestLaLista:
    def test_trae_los_activos_por_nombre(self, api: Api):
        _nuevo(api)
        nombres = [p["name"] for p in api.ok("GET", "/suppliers")]
        assert nombres == sorted(nombres)

    def test_el_desactivado_no_sale_salvo_que_se_pida(self, api: Api):
        proveedor = _nuevo(api)
        api.ok(
            "PUT",
            f"/suppliers/{proveedor['id']}",
            {"name": proveedor["name"], "payment_terms_days": 0, "is_active": False},
        )

        activos = {p["id"] for p in api.ok("GET", "/suppliers")}
        assert proveedor["id"] not in activos

        todos = {p["id"] for p in api.ok("GET", "/suppliers?incluir_inactivos=true")}
        assert proveedor["id"] in todos


class TestLaEdicion:
    def test_corrige_los_datos(self, api: Api):
        proveedor = _nuevo(api)
        cambiado = api.ok(
            "PUT",
            f"/suppliers/{proveedor['id']}",
            {
                "name": "Nombre corregido",
                "identification_type": "02",
                "identification": proveedor["identification"],
                "email": "cobros@mayorista.cr",
                "payment_terms_days": 60,
            },
        )
        assert cambiado["name"] == "Nombre corregido"
        assert cambiado["payment_terms_days"] == 60
        assert cambiado["email"] == "cobros@mayorista.cr"

    def test_conservar_su_propia_cedula_no_es_un_choque(self, api: Api):
        # El error de dedo obvio: comparar contra todos incluido uno mismo.
        proveedor = _nuevo(api)
        api.ok(
            "PUT",
            f"/suppliers/{proveedor['id']}",
            {"name": "Igual", "identification": proveedor["identification"]},
        )

    def test_tomarle_la_cedula_a_otro_no_pasa(self, api: Api):
        uno = _nuevo(api)
        otro = _nuevo(api)
        estado, cuerpo = api.call(
            "PUT",
            f"/suppliers/{otro['id']}",
            {"name": otro["name"], "identification": uno["identification"]},
        )
        assert codigo((estado, cuerpo), 400) == "supplier_identification_taken"

    def test_uno_que_no_existe_es_404(self, api: Api):
        estado, cuerpo = api.call("PUT", "/suppliers/999999", {"name": "Fantasma"})
        assert codigo((estado, cuerpo), 404) == "supplier_not_found"


class TestQuienPuede:
    def test_el_cajero_no_los_administra(self, api: Api, cajero: Api):
        estado, cuerpo = cajero.call("GET", "/suppliers")
        assert codigo((estado, cuerpo), 403) == "admin_only"

    def test_sin_sesion_no_se_entra(self, api: Api):
        estado, cuerpo = api.call("GET", "/suppliers", token=None)
        assert estado == 401


class TestElModuloDelPlan:
    """RN-49 y RN-50 sobre una ruta de verdad.

    La compañía de esta clase se da de alta con un plan **sin** compras, que es
    lo que no puede probarse con las del resto de la batería.
    """

    @pytest.fixture(scope="class")
    def sin_compras(self, api: Api) -> Api:
        marca = marca_unica()
        correo = f"sin.compras.{marca}@pruebas.ventasys.cr"
        bootstrap(
            afiliado=int(marca[-6:]),
            compania=1,
            nombre="Compañía sin el módulo de compras",
            email=correo,
            password="prueba123",
            rol="admin",
            nombre_persona="Sin",
            apellido="Compras",
            plan=f"Plan sin módulos {marca}",
            plan_max_usuarios=-1,
            # Sin `plan_modulos`: el plan nace sin ninguno, que es lo que hay
            # que probar.
        )
        cliente = Api(api.base)
        entrar(cliente, correo, "prueba123")
        return cliente

    def test_crear_uno_responde_el_codigo(self, sin_compras: Api):
        estado, cuerpo = sin_compras.call("POST", "/suppliers", {"name": "No debería entrar"})
        assert codigo((estado, cuerpo), 403) == "module_not_in_plan"
        # El módulo viaja como dato para que el POS arme la frase (RN-30).
        assert cuerpo["detail"]["module"] == "purchases"

    def test_pero_la_lista_se_puede_leer(self, sin_compras: Api):
        # RN-50: apagar un módulo no borra nada, lo deja en solo lectura. Una
        # compañía que bajó de plan sigue consultando a quién le compró.
        assert sin_compras.ok("GET", "/suppliers") == []
