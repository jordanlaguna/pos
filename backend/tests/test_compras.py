"""Abonos a proveedor contra la pila real (T-1010, RN-55 y RN-56).

Lo que las pruebas con dobles no pueden mirar: que la salida de caja quede
escrita **en la misma transacción** que el abono, y que el arqueo del turno baje
exactamente lo que se pagó. Eso último es el examen de RN-56: si la gaveta y el
abono no fueran la misma plata, el esperado del turno no se movería.
"""

from __future__ import annotations

import pytest

from tests.conftest import Api, codigo, entrar, marca_unica


@pytest.fixture(scope="module")
def proveedor(api: Api) -> dict:
    marca = marca_unica()
    return api.ok(
        "POST",
        "/suppliers",
        {
            "name": f"Mayorista de compras {marca}",
            "identification_type": "02",
            "identification": f"3{marca}",
            "payment_terms_days": 30,
        },
    )


@pytest.fixture
def admin_con_caja(api: Api) -> Api:
    """Un administrador aparte, con su propio turno de caja.

    Aparte del `api` de la batería a propósito: el turno se delimita por
    `user_id`, así que uno propio deja el arqueo de esta prueba limpio y no le
    abre una caja al administrador que usan las demás.

    Administrador y no cajero porque abonar es cosa de administración, y con
    caja propia porque RN-56 exige que el efectivo salga del turno de **quien
    paga**.
    """
    marca = marca_unica()
    correo = f"cp.{marca}@pruebas.ventasys.cr"
    api.registrar(
        {
            "name": "Compras",
            "lastName": "Caja",
            "secondName": marca,
            "identification": f"8{marca}",
            "birth_date": "1990-01-01",
            "telephone": "80000000",
            "email": correo,
            "password": "prueba123",
        }
    )
    api.ok("POST", "/users/membership", {"email": correo, "role": "admin"})

    suyo = Api(api.base)
    entrar(suyo, correo, "prueba123", aceptando_invitaciones=True)
    suyo.user_id = suyo.ok("GET", "/users/me")["id_user"]  # type: ignore[attr-defined]
    return suyo


def comprar(cliente: Api, proveedor: dict, producto, *, total_unitario=1000, **cambios) -> dict:
    """Una compra a crédito de una unidad. Devuelve el cuerpo de la respuesta."""
    cuerpo = {
        "document_number": f"FC-{marca_unica()}",
        "source": "manual",
        "user_id": cliente.user_id,  # type: ignore[attr-defined]
        "supplier_id": proveedor["id"],
        "document_date": "2026-09-10",
        "payment_terms": "credit",
        "payment_terms_days": 30,
        "lines": [
            {"id_product": producto["id_product"], "quantity": 1, "unit_cost": total_unitario}
        ],
    }
    cuerpo.update(cambios)
    return cliente.ok("POST", "/inventory/entry", cuerpo)


def esperado(cliente: Api) -> float:
    return cliente.ok("GET", "/cash/current")["expected_amount"]


class TestElAbono:
    def test_por_transferencia_baja_el_saldo(self, api: Api, proveedor, producto):
        compra = comprar(api, proveedor, producto("Comprado", 2000, 0))
        respuesta = api.ok(
            "POST",
            f"/purchases/{compra['id_entry']}/payments",
            {"amount": 400, "method": "transfer", "reference": "TRF-1"},
        )
        assert respuesta["balance"] == 600
        assert respuesta["cash_movement_id"] is None

        # El segundo abono ve lo que dejó el primero.
        segundo = api.ok(
            "POST",
            f"/purchases/{compra['id_entry']}/payments",
            {"amount": 600, "method": "transfer"},
        )
        assert segundo["balance"] == 0

    def test_abonar_de_mas_no_deja_nada(self, api: Api, proveedor, producto):
        compra = comprar(api, proveedor, producto("Comprado", 2000, 0))
        estado, cuerpo = api.call(
            "POST",
            f"/purchases/{compra['id_entry']}/payments",
            {"amount": 1000.01, "method": "transfer"},
        )
        assert codigo((estado, cuerpo), 400) == "payment_exceeds_balance"
        # Los dos montos viajan como datos para que el POS arme la frase (RN-30).
        assert cuerpo["detail"]["balance"] == "1000.00"

        # Y el saldo sigue entero: el «no» no escribió nada a medias.
        assert (
            api.ok(
                "POST",
                f"/purchases/{compra['id_entry']}/payments",
                {"amount": 1000, "method": "transfer"},
            )["balance"]
            == 0
        )

    def test_una_compra_que_no_existe(self, api: Api):
        estado, cuerpo = api.call(
            "POST", "/purchases/99999999/payments", {"amount": 1, "method": "transfer"}
        )
        assert codigo((estado, cuerpo), 404) == "entry_not_found"

    def test_una_entrada_sin_proveedor_no_es_una_compra(self, api: Api, producto):
        # No genera cuenta por pagar (RN-52): desde cuentas por pagar no existe.
        entrada = api.ok(
            "POST",
            "/inventory/entry",
            {
                "document_number": f"SIN-{marca_unica()}",
                "source": "manual",
                "user_id": api.user_id,  # type: ignore[attr-defined]
                "lines": [
                    {"id_product": producto("Comprado", 1000, 0)["id_product"], "quantity": 1, "unit_cost": 500}
                ],
            },
        )
        estado, cuerpo = api.call(
            "POST",
            f"/purchases/{entrada['id_entry']}/payments",
            {"amount": 100, "method": "transfer"},
        )
        assert codigo((estado, cuerpo), 404) == "entry_not_found"

    @pytest.mark.parametrize(
        "cuerpo,esperado_codigo",
        [
            ({"amount": 100, "method": "efectivo"}, "invalid_payment_method"),
            ({"amount": 0, "method": "transfer"}, "payment_not_positive"),
        ],
    )
    def test_lo_que_no_es_un_abono(self, api: Api, proveedor, producto, cuerpo, esperado_codigo):
        compra = comprar(api, proveedor, producto("Comprado", 2000, 0))
        estado, respuesta = api.call(
            "POST", f"/purchases/{compra['id_entry']}/payments", cuerpo
        )
        assert codigo((estado, respuesta), 400) == esperado_codigo


class TestElEfectivoSaleDeLaCaja:
    """RN-56 contra el arqueo de verdad."""

    def test_el_esperado_del_turno_baja_lo_que_se_pago(
        self, api: Api, admin_con_caja: Api, proveedor, producto
    ):
        compra = comprar(admin_con_caja, proveedor, producto("Comprado", 2000, 0))
        admin_con_caja.ok(
            "POST",
            "/cash/open",
            {"user_id": admin_con_caja.user_id, "opening_amount": 5000},  # type: ignore[attr-defined]
        )
        antes = esperado(admin_con_caja)

        respuesta = admin_con_caja.ok(
            "POST",
            f"/purchases/{compra['id_entry']}/payments",
            {"amount": 400, "method": "cash", "reason": "Pago de factura"},
        )

        assert respuesta["cash_movement_id"] is not None
        assert esperado(admin_con_caja) == antes - 400

        admin_con_caja.ok(
            "POST",
            "/cash/close",
            {
                "user_id": admin_con_caja.user_id,  # type: ignore[attr-defined]
                "closing_amount": esperado(admin_con_caja),
                "notes": None,
            },
        )

    def test_sin_caja_abierta_no_hay_pago_en_efectivo(self, api: Api, proveedor, producto):
        # El administrador de la batería no tiene turno abierto. RN-56 no deja
        # más salida que abrir la caja o pagar por transferencia.
        compra = comprar(api, proveedor, producto("Comprado", 2000, 0))
        estado, cuerpo = api.call(
            "POST",
            f"/purchases/{compra['id_entry']}/payments",
            {"amount": 400, "method": "cash", "reason": "Pago de factura"},
        )
        assert codigo((estado, cuerpo), 400) == "cash_no_open_session"

        # Y no quedó abonada: el saldo entero sigue ahí.
        assert (
            api.ok(
                "POST",
                f"/purchases/{compra['id_entry']}/payments",
                {"amount": 1000, "method": "transfer"},
            )["balance"]
            == 0
        )

    def test_no_se_saca_mas_efectivo_del_que_hay(
        self, api: Api, admin_con_caja: Api, proveedor, producto
    ):
        compra = comprar(
            admin_con_caja, proveedor, producto("Comprado", 9000, 0), total_unitario=5000
        )
        admin_con_caja.ok(
            "POST",
            "/cash/open",
            {"user_id": admin_con_caja.user_id, "opening_amount": 300},  # type: ignore[attr-defined]
        )

        estado, cuerpo = admin_con_caja.call(
            "POST",
            f"/purchases/{compra['id_entry']}/payments",
            {"amount": 400, "method": "cash", "reason": "Pago de factura"},
        )
        assert codigo((estado, cuerpo), 400) == "cash_insufficient"

        admin_con_caja.ok(
            "POST",
            "/cash/close",
            {
                "user_id": admin_con_caja.user_id,  # type: ignore[attr-defined]
                "closing_amount": 300,
                "notes": None,
            },
        )


class TestLaCompraDeContado:
    """El abono automático, que T-1009 dejó para acá."""

    def test_con_metodo_nace_pagada(self, api: Api, proveedor, producto):
        compra = comprar(
            api,
            proveedor,
            producto("Comprado", 2000, 0),
            payment_terms="cash",
            payment_terms_days=None,
            payment_method="transfer",
        )
        assert compra["id_payment"] is not None

        # No queda nada que abonar.
        estado, cuerpo = api.call(
            "POST",
            f"/purchases/{compra['id_entry']}/payments",
            {"amount": 1, "method": "transfer"},
        )
        assert codigo((estado, cuerpo), 400) == "payment_exceeds_balance"

    def test_sin_metodo_queda_con_saldo(self, api: Api, proveedor, producto):
        # No se inventa de dónde salió la plata (RN-56). Se abona después.
        compra = comprar(
            api,
            proveedor,
            producto("Comprado", 2000, 0),
            payment_terms="cash",
            payment_terms_days=None,
        )
        assert compra["id_payment"] is None
        assert (
            api.ok(
                "POST",
                f"/purchases/{compra['id_entry']}/payments",
                {"amount": 1000, "method": "transfer"},
            )["balance"]
            == 0
        )

    def test_en_efectivo_sin_caja_no_entra_ni_la_mercaderia(
        self, api: Api, proveedor, producto
    ):
        """Lo que hay que mirar de frente: la compra entera rebota.

        Registrarla y dejar el pago pendiente convertiría una compra de contado
        en una deuda que no existe. El «no» es accionable: se abre la caja, o se
        marca el pago como transferencia.
        """
        item = producto("Comprado", 2000, 0)
        estado, cuerpo = api.call(
            "POST",
            "/inventory/entry",
            {
                "document_number": f"FC-{marca_unica()}",
                "source": "manual",
                "user_id": api.user_id,  # type: ignore[attr-defined]
                "supplier_id": proveedor["id"],
                "payment_terms": "cash",
                "payment_method": "cash",
                "payment_reason": "Pago de factura",
                "lines": [{"id_product": item["id_product"], "quantity": 5, "unit_cost": 1000}],
            },
        )
        assert codigo((estado, cuerpo), 400) == "cash_no_open_session"

        # Ni la mercadería: la transacción se revirtió entera.
        assert api.ok("GET", f"/products/product/{item['barcode']}")["stock"] == 0


class TestAnularUnaCompra:
    """RF-46 y RN-57 contra la pila real.

    Es la misma ruta de siempre —`/inventory/entry/{id}/cancel`— y no una
    `/purchases/{id}/void` aparte: la compra es la entrada, así que anularla es
    el mismo acto sobre la misma fila. Dos rutas serían dos sitios donde
    escribir la regla de los abonos.
    """

    def test_sin_abonos_vuelve_el_stock_y_queda_el_motivo(
        self, api: Api, soporte: Api, proveedor, producto
    ):
        item = producto("Comprado", 2000, 0)
        compra = comprar(api, proveedor, item)
        assert api.ok("GET", f"/products/product/{item['barcode']}")["stock"] == 1

        api.ok(
            "POST",
            f"/inventory/entry/{compra['id_entry']}/cancel",
            {"reason": "El proveedor mandó otra cosa"},
        )

        assert api.ok("GET", f"/products/product/{item['barcode']}")["stock"] == 0
        assert api.ok("GET", f"/inventory/entry/{compra['id_entry']}")["status"] == "anulada"

        # Y quedó en bitácora, con el motivo. Es lo que le queda al negocio
        # cuando el proveedor reclame esa factura.
        lineas = soporte.ok("GET", "/support/audit?accion=anular_compra&limite=20")["lineas"]
        mia = [l for l in lineas if f"entrada {compra['id_entry']}," in (l["detalle"] or "")]
        assert mia, "la anulación no quedó en la bitácora"
        assert "El proveedor mandó otra cosa" in mia[0]["detalle"]

    def test_sin_motivo_no_se_anula_una_compra(self, api: Api, proveedor, producto):
        compra = comprar(api, proveedor, producto("Comprado", 2000, 0))
        estado, cuerpo = api.call("POST", f"/inventory/entry/{compra['id_entry']}/cancel")
        assert codigo((estado, cuerpo), 400) == "void_reason_required"

        # Y no se anuló a medias: sigue aplicada.
        assert api.ok("GET", f"/inventory/entry/{compra['id_entry']}")["status"] == "aplicada"

    def test_con_abonos_no_se_anula(self, api: Api, proveedor, producto):
        compra = comprar(api, proveedor, producto("Comprado", 2000, 0))
        api.ok(
            "POST",
            f"/purchases/{compra['id_entry']}/payments",
            {"amount": 400, "method": "transfer"},
        )

        estado, cuerpo = api.call(
            "POST", f"/inventory/entry/{compra['id_entry']}/cancel", {"reason": "Me arrepentí"}
        )
        assert codigo((estado, cuerpo), 400) == "purchase_has_payments"
        # Cuántos: deshacer uno o siete no es la misma tarea.
        assert cuerpo["detail"]["payments"] == 1

    def test_una_entrada_sin_proveedor_se_anula_sin_motivo(self, api: Api, producto):
        # La pantalla de entradas nunca pidió motivo, y sigue sin pedirlo: una
        # entrada no puede tener abonos y su anulación no le debe nada a nadie.
        item = producto("Comprado", 2000, 0)
        entrada = api.ok(
            "POST",
            "/inventory/entry",
            {
                "document_number": f"SIN-{marca_unica()}",
                "source": "manual",
                "user_id": api.user_id,  # type: ignore[attr-defined]
                "lines": [{"id_product": item["id_product"], "quantity": 3, "unit_cost": 500}],
            },
        )

        api.ok("POST", f"/inventory/entry/{entrada['id_entry']}/cancel")

        assert api.ok("GET", f"/products/product/{item['barcode']}")["stock"] == 0


class TestElModuloDelPlan:
    @pytest.fixture(scope="class")
    def sin_compras(self, api: Api) -> Api:
        from tests.conftest import bootstrap

        marca = marca_unica()
        correo = f"sc.abono.{marca}@pruebas.ventasys.cr"
        bootstrap(
            afiliado=int(marca[-6:]),
            compania=1,
            nombre="Compañía sin compras para abonar",
            email=correo,
            password="prueba123",
            rol="admin",
            nombre_persona="Sin",
            apellido="Abonos",
            plan=f"Plan sin módulos {marca}",
            plan_max_usuarios=-1,
        )
        cliente = Api(api.base)
        entrar(cliente, correo, "prueba123")
        cliente.user_id = cliente.ok("GET", "/users/me")["id_user"]  # type: ignore[attr-defined]
        return cliente

    @pytest.fixture(scope="class")
    def producto_propio(self, sin_compras: Api) -> dict:
        """Un producto de esa compañía, para poder cargarle una entrada."""
        marca = marca_unica()
        sin_compras.call("POST", "/categories/register_category", {"name": "Pruebas"})
        categoria = next(
            c["id"]
            for c in sin_compras.ok("GET", "/categories/categories_list")
            if c["name"] == "Pruebas"
        )
        cuerpo = {
            "name": f"Sin módulo {marca}",
            "description": "producto de prueba",
            "price": 1000,
            "stock": 0,
            "barcode": f"S{marca}",
            "created_at": "2026-01-01T00:00:00",
            "category_id": categoria,
        }
        sin_compras.ok("POST", "/products/add_product", cuerpo)
        return sin_compras.ok("GET", f"/products/product/{cuerpo['barcode']}")

    def test_abonar_sin_el_modulo_responde_el_codigo(self, sin_compras: Api):
        # Antes que el 404 de la compra: el plan se mira en la dependencia, así
        # que ni siquiera se llega a buscar el documento.
        estado, cuerpo = sin_compras.call(
            "POST", "/purchases/1/payments", {"amount": 100, "method": "transfer"}
        )
        assert codigo((estado, cuerpo), 403) == "module_not_in_plan"
        assert cuerpo["detail"]["module"] == "purchases"

    def test_registrar_una_compra_sin_el_modulo_tampoco(
        self, sin_compras: Api, producto_propio
    ):
        """El hueco que dejó T-1009 y que el usuario decidió cerrar.

        `POST /inventory/entry` con `supplier_id` es una compra (RN-52), y sin
        el módulo no entra. Solo lo alcanza quien **bajó** de plan —sin módulo
        no puede dar de alta proveedores—, que es justo el caso que describe
        RN-50.
        """
        estado, cuerpo = sin_compras.call(
            "POST",
            "/inventory/entry",
            {
                "document_number": f"NM-{marca_unica()}",
                "source": "manual",
                "user_id": sin_compras.user_id,  # type: ignore[attr-defined]
                "supplier_id": 1,
                "lines": [
                    {
                        "id_product": producto_propio["id_product"],
                        "quantity": 1,
                        "unit_cost": 100,
                    }
                ],
            },
        )
        assert codigo((estado, cuerpo), 403) == "module_not_in_plan"

    def test_pero_una_entrada_sin_proveedor_sigue_entrando(
        self, sin_compras: Api, producto_propio
    ):
        """La otra mitad, y la que importa de RN-50.

        Apagar Compras no le cierra el inventario a nadie: una entrada de ajuste
        no es una compra y nunca necesitó el módulo. Por eso el mismo endpoint
        responde distinto según traiga proveedor o no.
        """
        sin_compras.ok(
            "POST",
            "/inventory/entry",
            {
                "document_number": f"NM-{marca_unica()}",
                "source": "manual",
                "user_id": sin_compras.user_id,  # type: ignore[attr-defined]
                "lines": [
                    {
                        "id_product": producto_propio["id_product"],
                        "quantity": 3,
                        "unit_cost": 100,
                    }
                ],
            },
        )
        assert (
            sin_compras.ok("GET", f"/products/product/{producto_propio['barcode']}")["stock"]
            == 3
        )
