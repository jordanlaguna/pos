"""Abonos a proveedor contra la pila real (T-1010, RN-55 y RN-56).

Lo que las pruebas con dobles no pueden mirar: que la salida de caja quede
escrita **en la misma transacción** que el abono, y que el arqueo del turno baje
exactamente lo que se pagó. Eso último es el examen de RN-56: si la gaveta y el
abono no fueran la misma plata, el esperado del turno no se movería.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from tests.conftest import Api, afiliado_unico, codigo, entrar, marca_unica


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


class TestLasCuentasPorPagar:
    """RF-44 contra la pila real.

    El saldo no se guarda: es el total menos los abonos (RN-55). Estas pruebas
    miran que esa resta y la antigüedad lleguen a la respuesta, y sobre todo
    **qué queda fuera**: lo pagado, lo anulado y lo que no es compra.
    """

    def de_este(self, api: Api, proveedor, **filtros) -> dict | None:
        """El bloque de este proveedor, que es el único que esta clase mira.

        La batería comparte compañía, así que `/payables` trae también las
        compras de las otras pruebas: buscar la propia es lo que hace que el
        orden en que corren no importe.
        """
        ruta = "/payables" + (f"?supplier_id={filtros['supplier_id']}" if filtros else "")
        pagina = api.ok("GET", ruta)
        return next(
            (s for s in pagina["suppliers"] if s["supplier_id"] == proveedor["id"]), None
        )

    def test_una_compra_a_credito_aparece_con_su_saldo(self, api: Api, proveedor, producto):
        compra = comprar(api, proveedor, producto("Comprado", 2000, 0))
        api.ok(
            "POST",
            f"/purchases/{compra['id_entry']}/payments",
            {"amount": 400, "method": "transfer"},
        )

        mia = self.de_este(api, proveedor)
        fila = next(c for c in mia["purchases"] if c["entry_id"] == compra["id_entry"])

        assert (fila["total"], fila["paid"], fila["balance"]) == (1000, 400, 600)
        assert fila["due_date"] == "2026-10-10"

    def test_una_pagada_no_es_una_cuenta_por_pagar(self, api: Api, proveedor, producto):
        compra = comprar(api, proveedor, producto("Comprado", 2000, 0))
        api.ok(
            "POST",
            f"/purchases/{compra['id_entry']}/payments",
            {"amount": 1000, "method": "transfer"},
        )

        mia = self.de_este(api, proveedor) or {"purchases": []}
        assert compra["id_entry"] not in [c["entry_id"] for c in mia["purchases"]]

    def test_una_anulada_tampoco(self, api: Api, proveedor, producto):
        # Es lo que hace que anular revierta la cuenta por pagar (RN-57): el
        # saldo es implícito, así que basta con dejarla fuera de acá.
        compra = comprar(api, proveedor, producto("Comprado", 2000, 0))
        assert compra["id_entry"] in [
            c["entry_id"] for c in self.de_este(api, proveedor)["purchases"]
        ]

        api.ok(
            "POST",
            f"/inventory/entry/{compra['id_entry']}/cancel",
            {"reason": "Cargada dos veces"},
        )

        mia = self.de_este(api, proveedor) or {"purchases": []}
        assert compra["id_entry"] not in [c["entry_id"] for c in mia["purchases"]]

    def test_el_saldo_del_proveedor_es_la_suma_de_sus_compras(
        self, api: Api, proveedor, producto
    ):
        antes = self.de_este(api, proveedor)
        base = antes["balance"] if antes else 0
        comprar(api, proveedor, producto("Comprado", 2000, 0), total_unitario=700)

        mia = self.de_este(api, proveedor)
        assert mia["balance"] == round(base + 700, 2)
        assert mia["balance"] == round(sum(c["balance"] for c in mia["purchases"]), 2)

    def test_siempre_vienen_los_cuatro_tramos(self, api: Api):
        pagina = api.ok("GET", "/payables")
        assert [t["bucket"] for t in pagina["by_bucket"]] == [0, 30, 60, 90]

    def test_una_vencida_hace_45_dias_cae_en_31_60(self, api: Api, proveedor, producto):
        # La fecha de hoy la pone el servidor: con el reloj del cliente, dos
        # cajas verían tramos distintos del mismo saldo.
        hoy = date.fromisoformat(api.ok("GET", "/payables")["as_of"])
        # Un día de plazo desde hace 45: vence hace 44, que es el tramo 31–60.
        # Con plazo cero sería de contado y no vencería nunca.
        compra = comprar(
            api,
            proveedor,
            producto("Comprado", 2000, 0),
            document_date=(hoy - timedelta(days=45)).isoformat(),
            payment_terms_days=1,
        )

        fila = next(
            c
            for c in self.de_este(api, proveedor)["purchases"]
            if c["entry_id"] == compra["id_entry"]
        )
        assert fila["bucket"] == 30, "44 días de atraso tienen que caer en 31–60"
        assert fila["days_overdue"] == 44

    def test_el_filtro_por_proveedor_deja_solo_ese(self, api: Api, proveedor, producto):
        comprar(api, proveedor, producto("Comprado", 2000, 0))
        pagina = api.ok("GET", f"/payables?supplier_id={proveedor['id']}")
        assert [s["supplier_id"] for s in pagina["suppliers"]] == [proveedor["id"]]

    def test_una_entrada_sin_proveedor_no_es_una_cuenta_por_pagar(self, api: Api, producto):
        # No genera cuenta por pagar (RN-52), por mucho que haya movido stock.
        antes = api.ok("GET", "/payables")["total"]
        api.ok(
            "POST",
            "/inventory/entry",
            {
                "document_number": f"SIN-{marca_unica()}",
                "source": "manual",
                "user_id": api.user_id,  # type: ignore[attr-defined]
                "lines": [
                    {
                        "id_product": producto("Comprado", 1000, 0)["id_product"],
                        "quantity": 1,
                        "unit_cost": 500,
                    }
                ],
            },
        )
        assert api.ok("GET", "/payables")["total"] == antes


class TestElReporteDeCompras:
    """RF-45: el crédito fiscal del periodo, por tarifa.

    Todo se mide **por diferencia** y no contra un absoluto. La base de pruebas
    vive mientras viva la pila, así que dos corridas seguidas dejan el doble de
    compras del mismo día: un `assert reporte["tax"] == 130` pasa la primera vez
    y falla la segunda por una razón que no tiene nada que ver con el código.
    """

    @staticmethod
    def reporte(api: Api, desde: str, hasta: str | None = None) -> dict:
        return api.ok("GET", f"/reports/purchases?from={desde}&to={hasta or desde}")

    @staticmethod
    def tarifas(reporte: dict) -> dict[float, tuple[float, float]]:
        return {r["tax_rate"]: (r["base"], r["tax"]) for r in reporte["by_rate"]}

    def test_separa_las_bases_y_los_impuestos_por_tarifa(self, api: Api, proveedor, producto):
        item = producto("Comprado", 2000, 0)
        dia = "2026-03-15"
        antes = self.tarifas(self.reporte(api, dia))

        comprar(
            api,
            proveedor,
            item,
            document_date=dia,
            lines=[
                {"id_product": item["id_product"], "quantity": 1, "unit_cost": 1000,
                 "tax_rate": 13, "tax_amount": 130},
                {"id_product": item["id_product"], "quantity": 1, "unit_cost": 2000,
                 "tax_rate": 1, "tax_amount": 20},
            ],
        )
        despues = self.tarifas(self.reporte(api, dia))

        # El 1 % y el 13 % llegan separados: el promedio de los dos no es
        # ninguno, y el D-104 los pide por aparte.
        assert self.crecio(antes, despues, 1.0) == (2000, 20)
        assert self.crecio(antes, despues, 13.0) == (1000, 130)

    def test_el_periodo_es_el_de_la_fecha_del_documento(self, api: Api, proveedor, producto):
        """La regla que mueve una declaración de mes.

        Una factura del 28 que se digita el 3 es IVA del mes de la factura.
        Contarla por la fecha de carga la sacaría de su periodo y la metería en
        el siguiente, desplazando las dos declaraciones a la vez.
        """
        item = producto("Comprado", 2000, 0)
        abril_antes = self.reporte(api, "2026-04-01", "2026-04-30")["tax"]
        mayo_antes = self.reporte(api, "2026-05-01", "2026-05-31")["tax"]

        comprar(
            api,
            proveedor,
            item,
            document_date="2026-04-28",
            lines=[
                {"id_product": item["id_product"], "quantity": 1, "unit_cost": 5000,
                 "tax_rate": 13, "tax_amount": 650}
            ],
        )

        assert self.reporte(api, "2026-04-01", "2026-04-30")["tax"] - abril_antes == 650
        assert self.reporte(api, "2026-05-01", "2026-05-31")["tax"] - mayo_antes == 0, (
            "la factura de abril se contó en mayo: el reporte está mirando la "
            "fecha de carga y no la del documento"
        )

    def test_una_anulada_no_deja_credito_fiscal(self, api: Api, proveedor, producto):
        item = producto("Comprado", 2000, 0)
        dia = "2026-06-10"
        antes = self.reporte(api, dia)["tax"]

        compra = comprar(
            api,
            proveedor,
            item,
            document_date=dia,
            lines=[
                {"id_product": item["id_product"], "quantity": 1, "unit_cost": 1000,
                 "tax_rate": 13, "tax_amount": 130}
            ],
        )
        assert self.reporte(api, dia)["tax"] - antes == 130

        api.ok(
            "POST",
            f"/inventory/entry/{compra['id_entry']}/cancel",
            {"reason": "No llegó la mercadería"},
        )

        assert self.reporte(api, dia)["tax"] == antes

    def test_una_entrada_sin_proveedor_no_entra(self, api: Api, producto):
        # Sin documento de proveedor no hay crédito fiscal que acreditar, por
        # mucho que la entrada haya movido inventario (RN-52).
        item = producto("Comprado", 2000, 0)
        dia = "2026-07-20"
        antes = self.reporte(api, dia)["tax"]

        api.ok(
            "POST",
            "/inventory/entry",
            {
                "document_number": f"SIN-{marca_unica()}",
                "source": "manual",
                "user_id": api.user_id,  # type: ignore[attr-defined]
                "document_date": dia,
                "lines": [
                    {"id_product": item["id_product"], "quantity": 1, "unit_cost": 1000,
                     "tax_rate": 13, "tax_amount": 130}
                ],
            },
        )

        assert self.reporte(api, dia)["tax"] == antes

    @staticmethod
    def crecio(antes: dict, despues: dict, tarifa: float) -> tuple[float, float]:
        """Cuánto creció la base y el impuesto de una tarifa."""
        base_antes, impuesto_antes = antes.get(tarifa, (0, 0))
        base, impuesto = despues[tarifa]
        return round(base - base_antes, 2), round(impuesto - impuesto_antes, 2)


class TestElModuloDelPlan:
    @pytest.fixture(scope="class")
    def sin_compras(self, api: Api) -> Api:
        from tests.conftest import bootstrap

        marca = marca_unica()
        correo = f"sc.abono.{marca}@pruebas.ventasys.cr"
        bootstrap(
            afiliado=afiliado_unico(),
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
