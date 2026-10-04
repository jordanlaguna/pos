"""Las tasas de planilla por HTTP (T-1204, RF-56, RN-67).

`test_siembra_planilla.py` comprueba el archivo de datos contra lo publicado;
esto comprueba que llegó a la base al arrancar, que se lee a una fecha y que
soporte puede agregar una tasa pero no editar la que rige.

**Las tablas son del país y la base de pruebas sobrevive entre corridas**, así
que una tasa de verdad agregada acá cambiaría el cálculo de todas las pruebas
que vengan después, en esta corrida y en las siguientes. Las que se agregan son
reglas con un concepto que no existe (`prueba_…`), distinto en cada corrida, y
ninguna carga real se toca.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.payroll import REQUIRED_CONTRIBUTIONS, STALE_AFTER_DAYS
from app.infrastructure import payroll_rates_cr as cr

from .conftest import Api, codigo, marca_unica

CARGAS = {f"{c}:{p}" for c, p in REQUIRED_CONTRIBUTIONS["CR"]}


class TestLoQueRigeAUnaFecha:
    def test_la_api_arranca_con_las_tasas_sembradas(self, api: Api):
        tasas = api.ok("GET", f"/payroll/rates?on={cr.VERIFIED_AT.isoformat()}")
        cargas = {f"{t['concept']}:{t['payer']}" for t in tasas["rates"] if t["payer"] != "rule"}
        assert cargas == CARGAS
        assert tasas["missing"] == []
        assert len(tasas["brackets"]) == 5 and tasas["brackets"][-1]["upper"] is None
        assert {c["concept"]: c["amount"] for c in tasas["credits"]} == {"child": 1710, "spouse": 2590}
        assert len(tasas["severance"]) == 13

    def test_cada_tasa_dice_su_fuente_y_de_cuando_es(self, api: Api):
        tasas = api.ok("GET", "/payroll/rates")
        ivm = next(t for t in tasas["rates"] if t["concept"] == "ivm" and t["payer"] == "employee")
        assert ivm["value"] == 0.0433
        assert "CCSS" in ivm["source"]
        vieja = (date.today() - date.fromisoformat(ivm["verified_at"])).days > STALE_AFTER_DAYS
        assert ivm["stale"] is vieja

    def test_antes_de_2026_faltan_todas_las_cargas(self, api: Api):
        """Una corrida de 2025 no se podría calcular, y la pantalla lo dice."""
        tasas = api.ok("GET", "/payroll/rates?on=2025-12-31")
        assert set(tasas["missing"]) == CARGAS
        assert tasas["brackets"] == []

    def test_es_de_administracion(self, cajero: Api):
        estado, _ = cajero.call("GET", "/payroll/rates")
        assert estado == 403


def regla(concepto: str, desde: str, valor: float = 5, pagador: str = "rule") -> dict:
    return {
        "concept": concepto,
        "payer": pagador,
        "value": valor,
        "valid_from": desde,
        "source": "Prueba automática, no es una norma",
    }


class TestSoporteAgregaNoEdita:
    def test_una_tasa_nueva_entra_con_su_vigencia(self, soporte: Api, api: Api):
        concepto = f"prueba_{marca_unica()}"
        fila = soporte.ok("PUT", "/support/payroll/rates", regla(concepto, "2026-01-01"))
        assert fila["verified_at"] == date.today().isoformat()
        tasas = api.ok("GET", "/payroll/rates?on=2026-06-01")
        assert any(t["concept"] == concepto and t["value"] == 5 for t in tasas["rates"])

    def test_la_posterior_la_reemplaza_desde_su_fecha(self, soporte: Api, api: Api):
        concepto = f"prueba_{marca_unica()}"
        soporte.ok("PUT", "/support/payroll/rates", regla(concepto, "2026-01-01", 5))
        soporte.ok("PUT", "/support/payroll/rates", regla(concepto, "2026-07-01", 7))
        valor = lambda on: next(  # noqa: E731
            t["value"] for t in api.ok("GET", f"/payroll/rates?on={on}")["rates"] if t["concept"] == concepto
        )
        assert (valor("2026-06-30"), valor("2026-07-01")) == (5, 7)

    def test_la_misma_fecha_o_una_anterior_no_entra(self, soporte: Api):
        """Una tasa no se edita: reescribir la vigente es reescribir corridas."""
        concepto = f"prueba_{marca_unica()}"
        soporte.ok("PUT", "/support/payroll/rates", regla(concepto, "2026-03-01"))
        for desde in ("2026-03-01", "2026-02-01"):
            respuesta = soporte.call("PUT", "/support/payroll/rates", regla(concepto, desde, 9))
            assert codigo(respuesta, 409) == "payroll_rate_not_newer"
            assert respuesta[1]["detail"]["latest"] == "2026-03-01"

    def test_una_carga_es_una_fraccion(self, soporte: Api):
        respuesta = soporte.call("PUT", "/support/payroll/rates", regla(f"prueba_{marca_unica()}", "2026-01-01", 5.5, "employee"))
        assert codigo(respuesta, 400) == "invalid_payroll_rate"
        assert respuesta[1]["detail"]["field"] == "value"

    def test_un_pagador_que_no_existe(self, soporte: Api):
        respuesta = soporte.call("PUT", "/support/payroll/rates", regla(f"prueba_{marca_unica()}", "2026-01-01", 1, "state"))
        assert codigo(respuesta, 400) == "invalid_payroll_rate"

    def test_queda_en_la_bitacora(self, soporte: Api):
        concepto = f"prueba_{marca_unica()}"
        soporte.ok("PUT", "/support/payroll/rates", regla(concepto, "2026-01-01"))
        bitacora = soporte.ok("GET", "/support/audit?accion=tasa_planilla")
        assert any(concepto in (linea.get("detalle") or "") for linea in bitacora["lineas"])

    def test_un_administrador_no_puede(self, api: Api):
        respuesta = api.call("PUT", "/support/payroll/rates", regla(f"prueba_{marca_unica()}", "2026-01-01"))
        assert codigo(respuesta, 403) == "support_only"


def tramos(desde: str, *filas) -> dict:
    return {
        "valid_from": desde,
        "brackets": [{"lower": a, "upper": b, "rate": t} for a, b, t in filas],
        "child_credit": "1800",
        "spouse_credit": "2700",
        "source": "Prueba automática, no es un decreto",
    }


BUENOS = (("0", "950000", "0"), ("950000", "1400000", "0.10"), ("1400000", None, "0.15"))


class TestLosTramosDelAnoSiguiente:
    """T-1221: el decreto sale cada diciembre y soporte lo carga con su vigencia."""

    @pytest.fixture(scope="class")
    def enero(self, api: Api) -> date:
        """El 1 de enero siguiente al juego más nuevo que haya. Una corrida
        anterior de esta prueba pudo dejar el suyo, y un juego no se edita.

        Se pregunta por una fecha lejana y no por hoy: hoy rige el juego de este
        año, y el que dejó la corrida anterior es del siguiente."""
        vigentes = api.ok("GET", "/payroll/rates?on=2099-12-31")["brackets"]
        ultimo = max(date.fromisoformat(t["valid_from"]) for t in vigentes)
        return date(ultimo.year + 1, 1, 1)

    def test_el_juego_nuevo_rige_desde_su_fecha_y_el_viejo_hasta_el_dia_antes(self, soporte: Api, api: Api, enero: date):
        viejo = api.ok("GET", f"/payroll/rates?on={enero.isoformat()}")
        salida = soporte.ok("PUT", "/support/payroll/brackets", tramos(enero.isoformat(), *BUENOS))
        assert [t["lower"] for t in salida["brackets"]] == [0, 950000, 1400000]
        assert {c["concept"]: c["amount"] for c in salida["credits"]} == {"child": 1800, "spouse": 2700}

        antes = api.ok("GET", f"/payroll/rates?on={(enero - timedelta(days=1)).isoformat()}")
        despues = api.ok("GET", f"/payroll/rates?on={enero.isoformat()}")
        assert [t["lower"] for t in antes["brackets"]] == [t["lower"] for t in viejo["brackets"]]
        assert [(t["lower"], t["upper"], t["rate"]) for t in despues["brackets"]] == [
            (0, 950000, 0),
            (950000, 1400000, 0.1),
            (1400000, None, 0.15),
        ]
        assert despues["brackets"][0]["verified_at"] == date.today().isoformat()

    def test_un_juego_con_hueco_o_que_no_empieza_en_cero_se_rechaza(self, soporte: Api, enero: date):
        futuro = date(enero.year + 5, 1, 1).isoformat()
        con_hueco = soporte.call("PUT", "/support/payroll/brackets", tramos(futuro, ("0", "900000", "0"), ("950000", None, "0.1")))
        assert codigo(con_hueco, 400) == "invalid_tax_brackets"
        assert (con_hueco[1]["detail"]["reason"], con_hueco[1]["detail"]["index"]) == ("gap", 1)
        sin_cero = soporte.call("PUT", "/support/payroll/brackets", tramos(futuro, ("100", "900000", "0"), ("900000", None, "0.1")))
        assert codigo(sin_cero, 400) == "invalid_tax_brackets"
        cerrado = soporte.call("PUT", "/support/payroll/brackets", tramos(futuro, ("0", "900000", "0"), ("900000", "950000", "0.1")))
        assert con_hueco[1]["detail"]["reason"] == "gap" and codigo(cerrado, 400) == "invalid_tax_brackets"

    def test_el_juego_vigente_no_se_edita(self, soporte: Api, enero: date):
        respuesta = soporte.call("PUT", "/support/payroll/brackets", tramos(enero.isoformat(), *BUENOS))
        assert codigo(respuesta, 409) == "payroll_rate_not_newer"
        assert respuesta[1]["detail"]["concept"] == "income_tax_brackets"

    def test_queda_en_la_bitacora_y_un_administrador_no_puede(self, soporte: Api, api: Api, enero: date):
        bitacora = soporte.ok("GET", "/support/audit?accion=tramos_renta")
        assert any(enero.isoformat() in (linea.get("detalle") or "") for linea in bitacora["lineas"])
        respuesta = api.call("PUT", "/support/payroll/brackets", tramos("2099-01-01", *BUENOS))
        assert codigo(respuesta, 403) == "support_only"
