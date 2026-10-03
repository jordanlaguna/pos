"""Planilla por HTTP (F12: T-1217, T-1205, T-1218, T-1206).

Contra la pila de pruebas, con las tasas **de verdad** que siembra la API
(T-1204): acá no se comprueba la aritmética —eso está en el dominio con cifras
inventadas— sino que la corrida tome lo que debe, lo congele, pase por sus
estados y deje su asiento y su bitácora.

Cada clase trabaja sobre una **compañía propia**, dada de alta con el mismo
`bootstrap.py` de siempre: una prueba que paga una planilla en la compañía A
le cambiaría el libro a media batería.

**Las tasas son del país y la base sobrevive entre corridas.** La única que se
agrega acá es un rubro patronal con un concepto que no existe (`prueba_…`),
con vigencia de ayer: sirve para ver que la corrida pagada no cambia y la
nueva sí, y a nadie más le importa.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

import pytest

from tests.conftest import Api, afiliado_unico, bootstrap, codigo, entrar, marca_unica

pytestmark = pytest.mark.characterization

HOY = date.today()
AYER = HOY - timedelta(days=1)


def compania_propia(api: Api, etiqueta: str, *, modulos: str = "payroll,accounting") -> Api:
    marca = marca_unica()
    correo = f"{etiqueta}.{marca}@pruebas.ventasys.cr"
    bootstrap(
        afiliado=afiliado_unico(),
        compania=1,
        nombre=f"Compañía {etiqueta} {marca}",
        email=correo,
        password="prueba123",
        rol="admin",
        nombre_persona="Pla",
        apellido="Nilla",
        cedula=marca[-9:],
        plan=f"Plan {etiqueta} {marca}",
        plan_max_usuarios="-1",
        plan_modulos=modulos,
    )
    cliente = Api(api.base)
    entrar(cliente, correo, "prueba123")
    cliente.user_id = cliente.ok("GET", "/users/me")["id_user"]  # type: ignore[attr-defined]
    return cliente


def jornada_quincenal(cliente: Api, nombre: str = "Quincenal") -> dict:
    return cliente.ok(
        "POST",
        "/payroll/schedules",
        {"name": nombre, "frequency": "semimonthly", "shift": "day", "first_cut_day": 15},
    )


def puesto(cliente: Api, nombre: str = "Cajera") -> dict:
    return cliente.ok("POST", "/payroll/positions", {"name": nombre, "ccss_code": "4211", "ins_code": "52"})


def poliza(cliente: Api, numero: str = "RT-1", prima: str = "0.0146", **extra) -> dict:
    return cliente.ok("POST", "/payroll/policies", {"number": numero, "rt_rate": prima, **extra})


def ficha(cedula: str, **cambios) -> dict:
    datos = {
        "identification_type": "national",
        "identification": cedula,
        "first_name": "Ana",
        "last_name_1": "Mora",
        "last_name_2": "Solís",
        "birth_date": "1990-05-20",
        "gender": "F",
        "marital_status": "single",
        "nationality": "CR",
        "hired_on": "2025-06-01",
        "iban": "CR05015202001026284066",
    }
    datos.update(cambios)
    return datos


def contratar(cliente: Api, employee_id: int, schedule_id: int, position_id: int, salario: str, **cambios) -> dict:
    cuerpo = {
        "employee_id": employee_id,
        "schedule_id": schedule_id,
        "position_id": position_id,
        "valid_from": "2025-06-01",
        "period_salary": salario,
    }
    cuerpo.update(cambios)
    return cliente.ok("POST", "/payroll/contracts", cuerpo)


def proximo_corte_quincenal(desde: date) -> date:
    """El primer corte (15 o fin de mes) que no sea anterior a `desde`."""
    if desde.day <= 15:
        return desde.replace(day=15)
    return desde.replace(day=calendar.monthrange(desde.year, desde.month)[1])


# ----------------------------------------------------------- configuración


class TestLaConfiguracion:
    @pytest.fixture(scope="class")
    def empresa(self, api: Api) -> Api:
        return compania_propia(api, "conf")

    def test_nace_vacia(self, empresa: Api):
        assert empresa.ok("GET", "/payroll/settings") == {"employer_number": None, "ina_exempt": False}

    def test_el_numero_patronal_y_el_ina(self, empresa: Api):
        guardado = empresa.ok(
            "PUT", "/payroll/settings", {"employer_number": " 2-03101702934-001-001 ", "ina_exempt": True}
        )
        assert guardado == {"employer_number": "2-03101702934-001-001", "ina_exempt": True}
        assert empresa.ok("GET", "/payroll/settings") == guardado

    def test_un_numero_que_no_lo_es(self, empresa: Api):
        respuesta = empresa.call("PUT", "/payroll/settings", {"employer_number": "2 03101702934"})
        assert codigo(respuesta, 400) == "invalid_payroll_settings"
        assert respuesta[1]["detail"]["field"] == "employer_number"

    def test_guardar_la_configuracion_del_pos_no_la_borra(self, empresa: Api):
        """Es la sección de otra puerta: `save_settings` la conserva aunque el
        POS no la mande (el mismo defecto que apagaba la contabilidad)."""
        empresa.ok("PUT", "/payroll/settings", {"employer_number": "203101702934", "ina_exempt": True})
        empresa.ok("PUT", "/settings/", {"data": {"currency": {"code": "CRC"}}, "logo": None, "keep_logo": True})
        assert empresa.ok("GET", "/payroll/settings")["employer_number"] == "203101702934"
        # Y mandarla por ahí tampoco la escribe.
        empresa.ok(
            "PUT",
            "/settings/",
            {"data": {"payroll": {"employer_number": "999999999"}}, "logo": None, "keep_logo": True},
        )
        assert empresa.ok("GET", "/payroll/settings")["employer_number"] == "203101702934"

    def test_es_de_administracion(self, cajero: Api):
        estado, _ = cajero.call("GET", "/payroll/settings")
        assert estado == 403


class TestLasJornadas:
    @pytest.fixture(scope="class")
    def empresa(self, api: Api) -> Api:
        return compania_propia(api, "jornadas")

    def test_la_quincenal_con_sus_horas_por_omision(self, empresa: Api):
        fila = jornada_quincenal(empresa)
        assert (fila["frequency"], fila["first_cut_day"], fila["hours_per_day"], fila["is_active"]) == (
            "semimonthly",
            15,
            8,
            True,
        )
        assert [j["name"] for j in empresa.ok("GET", "/payroll/schedules")] == ["Quincenal"]

    def test_cada_periodicidad_pide_su_corte_y_solo_ese(self, empresa: Api):
        respuesta = empresa.call(
            "POST", "/payroll/schedules", {"name": "Mensual", "frequency": "monthly", "first_cut_day": 15}
        )
        assert codigo(respuesta, 400) == "invalid_schedule"
        assert (respuesta[1]["detail"]["field"], respuesta[1]["detail"]["reason"]) == ("first_cut_day", "unexpected")
        respuesta = empresa.call("POST", "/payroll/schedules", {"name": "Semanal", "frequency": "weekly"})
        assert codigo(respuesta, 400) == "invalid_schedule"

    def test_el_nombre_no_se_repite(self, empresa: Api):
        respuesta = empresa.call(
            "POST", "/payroll/schedules", {"name": "Quincenal", "frequency": "monthly"}
        )
        assert codigo(respuesta, 409) == "payroll_name_taken"
        assert respuesta[1]["detail"] == {"code": "payroll_name_taken", "resource": "schedules", "name": "Quincenal"}

    def test_se_renombra_y_se_apaga(self, empresa: Api):
        fila = empresa.ok("GET", "/payroll/schedules")[0]
        cambiada = empresa.ok("PUT", f"/payroll/schedules/{fila['id']}", {"name": "Cajas", "is_active": False})
        assert (cambiada["name"], cambiada["is_active"]) == ("Cajas", False)
        assert codigo(empresa.call("PUT", "/payroll/schedules/99999", {"name": "x"}), 404) == "schedule_not_found"


class TestLosPuestosYLasPolizas:
    @pytest.fixture(scope="class")
    def empresa(self, api: Api) -> Api:
        return compania_propia(api, "puestos")

    def test_el_puesto_con_sus_dos_codigos(self, empresa: Api):
        fila = puesto(empresa)
        assert (fila["ccss_code"], fila["ins_code"], fila["is_active"]) == ("4211", "52", True)
        respuesta = empresa.call("POST", "/payroll/positions", {"name": "Bodega", "ccss_code": "42", "ins_code": "52"})
        assert codigo(respuesta, 400) == "invalid_payroll_settings"
        assert respuesta[1]["detail"]["field"] == "ccss_code"
        respuesta = empresa.call("POST", "/payroll/positions", {"name": "Cajera", "ccss_code": "4211", "ins_code": "52"})
        assert codigo(respuesta, 409) == "payroll_name_taken"
        apagado = empresa.ok("PUT", f"/payroll/positions/{fila['id']}", {"is_active": False})
        assert apagado["is_active"] is False
        assert codigo(empresa.call("PUT", "/payroll/positions/99999", {"name": "x"}), 404) == "position_not_found"

    def test_la_primera_poliza_queda_por_omision(self, empresa: Api):
        primera = poliza(empresa, "RT-1")
        segunda = poliza(empresa, "RT-2", "0.0300")
        assert (primera["is_default"], segunda["is_default"]) == (True, False)
        cambiada = empresa.ok("PUT", f"/payroll/policies/{segunda['id']}", {"is_default": True})
        assert cambiada["is_default"] is True
        por_omision = [p["number"] for p in empresa.ok("GET", "/payroll/policies") if p["is_default"]]
        assert por_omision == ["RT-2"]

    def test_lo_que_no_es_una_poliza(self, empresa: Api):
        respuesta = empresa.call("POST", "/payroll/policies", {"number": "RT-3", "rt_rate": "1.46"})
        assert codigo(respuesta, 400) == "invalid_payroll_settings"
        assert respuesta[1]["detail"]["field"] == "rt_rate"
        assert codigo(empresa.call("POST", "/payroll/policies", {"number": "RT-1", "rt_rate": "0.01"}), 409) == "payroll_name_taken"
        assert codigo(empresa.call("PUT", "/payroll/policies/99999", {"rt_rate": "0.01"}), 404) == "policy_not_found"


# --------------------------------------------------------------- empleados


class TestLosEmpleados:
    @pytest.fixture(scope="class")
    def empresa(self, api: Api) -> Api:
        return compania_propia(api, "empleados")

    @pytest.fixture(scope="class")
    def catalogo(self, empresa: Api) -> dict:
        return {"jornada": jornada_quincenal(empresa), "puesto": puesto(empresa), "poliza": poliza(empresa)}

    def test_el_alta_sin_contrato(self, empresa: Api, catalogo: dict):
        fila = empresa.ok("POST", "/payroll/employees", ficha("102340567"))
        assert (fila["first_name"], fila["last_name_2"], fila["is_active"], fila["contract"]) == ("Ana", "Solís", True, None)
        assert [e["identification"] for e in empresa.ok("GET", "/payroll/employees")] == ["102340567"]
        assert empresa.ok("GET", f"/payroll/employees/{fila['id']}")["id"] == fila["id"]

    def test_lo_que_la_ccss_rechazaria(self, empresa: Api):
        respuesta = empresa.call("POST", "/payroll/employees", ficha("102340567"))
        assert codigo(respuesta, 409) == "employee_identification_taken"
        respuesta = empresa.call("POST", "/payroll/employees", ficha("1-0234-0568"))
        assert codigo(respuesta, 400) == "invalid_employee"
        assert (respuesta[1]["detail"]["field"], respuesta[1]["detail"]["reason"]) == ("identification", "not_digits")
        respuesta = empresa.call("POST", "/payroll/employees", ficha("102340569", gender="X"))
        assert codigo(respuesta, 400) == "invalid_employee"
        assert codigo(empresa.call("GET", "/payroll/employees/99999"), 404) == "employee_not_found"

    def test_se_edita(self, empresa: Api):
        empleado = empresa.ok("GET", "/payroll/employees")[0]
        cambiado = empresa.ok("PUT", f"/payroll/employees/{empleado['id']}", {"dependent_children": 2, "phone": "88888888"})
        assert (cambiado["dependent_children"], cambiado["phone"]) == (2, "88888888")

    def test_el_contrato_y_el_aumento(self, empresa: Api, catalogo: dict):
        empleado = empresa.ok("GET", "/payroll/employees")[0]
        primero = contratar(empresa, empleado["id"], catalogo["jornada"]["id"], catalogo["puesto"]["id"], "300000")
        assert (primero["valid_from"], primero["valid_to"], primero["period_salary"]) == ("2025-06-01", None, 300000)
        assert empresa.ok("GET", f"/payroll/employees/{empleado['id']}")["contract"]["id"] == primero["id"]

        # Uno nuevo cierra el anterior el día antes.
        segundo = contratar(
            empresa, empleado["id"], catalogo["jornada"]["id"], catalogo["puesto"]["id"], "350000", valid_from="2026-01-01"
        )
        contratos = empresa.ok("GET", f"/payroll/contracts?employee={empleado['id']}")
        assert [(c["valid_from"], c["valid_to"], c["period_salary"]) for c in contratos] == [
            ("2025-06-01", "2025-12-31", 300000),
            ("2026-01-01", None, 350000),
        ]
        assert segundo["id"] == contratos[1]["id"]

    def test_lo_que_no_es_un_contrato(self, empresa: Api, catalogo: dict):
        empleado = empresa.ok("GET", "/payroll/employees")[0]
        jornada, puesto_ = catalogo["jornada"]["id"], catalogo["puesto"]["id"]
        respuesta = empresa.call(
            "POST",
            "/payroll/contracts",
            {"employee_id": empleado["id"], "schedule_id": jornada, "position_id": puesto_, "valid_from": "2026-01-01", "period_salary": "1"},
        )
        assert codigo(respuesta, 400) == "invalid_contract"
        assert respuesta[1]["detail"]["reason"] == "overlaps"
        respuesta = empresa.call(
            "POST",
            "/payroll/contracts",
            {"employee_id": empleado["id"], "schedule_id": 99999, "position_id": puesto_, "valid_from": "2026-03-01", "period_salary": "1"},
        )
        assert codigo(respuesta, 404) == "schedule_not_found"
        respuesta = empresa.call(
            "POST",
            "/payroll/contracts",
            {"employee_id": empleado["id"], "schedule_id": jornada, "position_id": puesto_, "valid_from": "2026-03-01", "period_salary": "0"},
        )
        assert codigo(respuesta, 400) == "invalid_contract"

    def test_la_baja_cierra_el_contrato_y_abre_la_liquidacion(self, empresa: Api):
        empleado = empresa.ok("GET", "/payroll/employees")[0]
        respuesta = empresa.call(
            "POST", f"/payroll/employees/{empleado['id']}/terminate", {"terminated_on": "2026-02-10", "cause": "se_fue"}
        )
        assert codigo(respuesta, 400) == "invalid_employee"

        baja = empresa.ok(
            "POST", f"/payroll/employees/{empleado['id']}/terminate", {"terminated_on": "2026-02-10", "cause": "resignation"}
        )
        assert (baja["employee"]["terminated_on"], baja["employee"]["termination_cause"], baja["employee"]["is_active"]) == (
            "2026-02-10",
            "resignation",
            False,
        )
        assert baja["employee"]["contract"]["valid_to"] == "2026-02-10"
        liquidacion = empresa.ok("GET", f"/payroll/runs/{baja['settlement_run_id']}")
        assert (liquidacion["kind"], liquidacion["status"], liquidacion["period_to"]) == ("settlement", "draft", "2026-02-10")
        historial = empresa.ok("GET", f"/payroll/employees/{empleado['id']}/actions")
        assert [(a["kind"], a["starts_on"], a["source"]) for a in historial] == [("termination", "2026-02-10", "system")]

        otra_vez = empresa.call(
            "POST", f"/payroll/employees/{empleado['id']}/terminate", {"terminated_on": "2026-03-10", "cause": "resignation"}
        )
        assert codigo(otra_vez, 409) == "employee_terminated"
        # Y una acción después de la salida tampoco entra.
        respuesta = empresa.call(
            "POST", "/payroll/actions", {"employee_id": empleado["id"], "kind": "bonus", "starts_on": "2026-02-11", "amount": "1000"}
        )
        assert codigo(respuesta, 409) == "employee_terminated"


# ---------------------------------------------------------------- acciones


class TestLasAcciones:
    @pytest.fixture(scope="class")
    def empresa(self, api: Api) -> Api:
        return compania_propia(api, "acciones")

    @pytest.fixture(scope="class")
    def empleado(self, empresa: Api) -> dict:
        jornada = jornada_quincenal(empresa)
        puesto_ = puesto(empresa)
        poliza(empresa)
        fila = empresa.ok("POST", "/payroll/employees", ficha("203450678", first_name="Luis", gender="M"))
        contratar(empresa, fila["id"], jornada["id"], puesto_["id"], "300000")
        return fila

    def accion(self, empresa: Api, empleado: dict, **datos) -> tuple[int, object]:
        return empresa.call("POST", "/payroll/actions", {"employee_id": empleado["id"], **datos})

    def test_se_registra_y_queda_en_el_historial(self, empresa: Api, empleado: dict):
        estado, fila = self.accion(empresa, empleado, kind="bonus", starts_on="2026-01-10", amount="20000", memo="inventario")
        assert estado == 200, fila
        assert (fila["kind"], fila["amount"], fila["memo"], fila["applied"], fila["applied_total"], fila["balance"]) == (
            "bonus",
            20000,
            "inventario",
            [],
            0,
            None,
        )
        assert fila["created_by"] == empresa.user_id  # type: ignore[attr-defined]
        ids = [a["id"] for a in empresa.ok("GET", f"/payroll/employees/{empleado['id']}/actions")]
        assert fila["id"] in ids

    def test_lo_que_no_se_registra(self, empresa: Api, empleado: dict):
        respuesta = self.accion(empresa, empleado, kind="overtime", starts_on="2026-01-10")
        assert codigo(respuesta, 400) == "invalid_action"
        assert (respuesta[1]["detail"]["field"], respuesta[1]["detail"]["reason"]) == ("hours", "required")
        respuesta = self.accion(empresa, empleado, kind="termination", starts_on="2026-01-10")
        assert codigo(respuesta, 400) == "invalid_action"
        respuesta = empresa.call("POST", "/payroll/actions", {"employee_id": 99999, "kind": "bonus", "starts_on": "2026-01-10", "amount": "1"})
        assert codigo(respuesta, 404) == "employee_not_found"
        respuesta = self.accion(empresa, empleado, kind="bonus", starts_on="2025-01-10", amount="1")
        assert codigo(respuesta, 409) == "contract_missing"

    def test_se_edita_mientras_nadie_la_aplique(self, empresa: Api, empleado: dict):
        _, fila = self.accion(empresa, empleado, kind="overtime", starts_on="2026-01-12", hours="4")
        cambiada = empresa.ok("PUT", f"/payroll/actions/{fila['id']}", {"starts_on": "2026-01-13", "hours": "6"})
        assert (cambiada["starts_on"], cambiada["hours"], cambiada["kind"]) == ("2026-01-13", 6, "overtime")
        assert codigo(empresa.call("PUT", "/payroll/actions/99999", {"starts_on": "2026-01-13"}), 404) == "action_not_found"

    def test_se_anula_con_otra_que_la_referencia(self, empresa: Api, empleado: dict):
        _, fila = self.accion(empresa, empleado, kind="bonus", starts_on="2026-01-14", amount="5000")
        anulacion = empresa.ok("POST", f"/payroll/actions/{fila['id']}/cancel", {"memo": "no era"})
        assert (anulacion["cancels_action_id"], anulacion["kind"], anulacion["memo"]) == (fila["id"], "bonus", "no era")
        original = next(a for a in empresa.ok("GET", f"/payroll/employees/{empleado['id']}/actions") if a["id"] == fila["id"])
        assert original["cancelled_by"] == anulacion["id"]
        assert codigo(empresa.call("PUT", f"/payroll/actions/{fila['id']}", {"starts_on": "2026-01-14", "amount": "1"}), 409) == "action_already_cancelled"
        assert codigo(empresa.call("POST", f"/payroll/actions/{fila['id']}/cancel"), 409) == "action_already_cancelled"
        respuesta = empresa.call("POST", f"/payroll/actions/{anulacion['id']}/cancel")
        assert codigo(respuesta, 409) == "action_not_editable"
        assert respuesta[1]["detail"]["reason"] == "cancellation"

    def test_se_suspende_solo_la_recurrente(self, empresa: Api, empleado: dict):
        _, unica = self.accion(empresa, empleado, kind="deduction", starts_on="2026-01-01", amount="5000")
        assert codigo(empresa.call("POST", f"/payroll/actions/{unica['id']}/suspend", {"reason": "pausa"}), 409) == "action_not_recurring"
        _, prestamo = self.accion(
            empresa, empleado, kind="deduction", starts_on="2026-01-01", amount="25000", total_amount="300000", is_recurring=True
        )
        assert prestamo["balance"] == 300000
        suspendido = empresa.ok("POST", f"/payroll/actions/{prestamo['id']}/suspend", {"reason": "pidió pausa"})
        assert (suspendido["suspended_by"], suspendido["suspension_reason"]) == (empresa.user_id, "pidió pausa")  # type: ignore[attr-defined]
        assert suspendido["suspended_at"] is not None
        assert codigo(empresa.call("POST", f"/payroll/actions/{prestamo['id']}/suspend", {"reason": "otra vez"}), 409) == "action_already_suspended"

    def test_el_aumento_cierra_el_contrato_y_abre_otro(self, empresa: Api, empleado: dict):
        estado, fila = self.accion(empresa, empleado, kind="raise", starts_on="2026-03-01", new_salary="330000")
        assert estado == 200, fila
        contratos = empresa.ok("GET", f"/payroll/contracts?employee={empleado['id']}")
        assert [(c["valid_to"], c["period_salary"]) for c in contratos] == [("2026-02-28", 300000), (None, 330000)]
        respuesta = empresa.call("PUT", f"/payroll/actions/{fila['id']}", {"starts_on": "2026-03-02"})
        assert codigo(respuesta, 409) == "action_not_editable"
        assert respuesta[1]["detail"]["reason"] == "contract"


# ----------------------------------------------------------------- corridas


class TestLasCorridas:
    """El recorrido entero: crear, calcular, aprobar, pagar, con libro y bitácora."""

    @pytest.fixture(scope="class")
    def empresa(self, api: Api) -> Api:
        cliente = compania_propia(api, "corridas")
        cliente.ok("POST", "/accounting/activate", {"template": "commerce", "start_date": "2026-01-01"})
        return cliente

    @pytest.fixture(scope="class")
    def mundo(self, empresa: Api) -> dict:
        jornada = jornada_quincenal(empresa)
        puesto_ = puesto(empresa)
        poliza(empresa)
        # Un millón al mes: cae en el tramo del 10 % y la renta no es cero.
        empleada = empresa.ok("POST", "/payroll/employees", ficha("304560789"))
        contratar(empresa, empleada["id"], jornada["id"], puesto_["id"], "500000")
        empresa.ok(
            "POST",
            "/payroll/actions",
            {"employee_id": empleada["id"], "kind": "deduction", "starts_on": "2026-01-01", "amount": "10000"},
        )
        return {"jornada": jornada, "empleada": empleada}

    @pytest.fixture(scope="class")
    def corrida(self, empresa: Api, mundo: dict) -> dict:
        return empresa.ok("POST", "/payroll/runs", {"schedule_id": mundo["jornada"]["id"], "cut_date": "2026-01-15"})

    def test_el_periodo_sale_del_corte(self, empresa: Api, mundo: dict, corrida: dict):
        assert (corrida["kind"], corrida["status"], corrida["period_from"], corrida["period_to"], corrida["pay_date"]) == (
            "regular",
            "draft",
            "2026-01-01",
            "2026-01-15",
            "2026-01-15",
        )
        assert (corrida["schedule_name"], corrida["employees"], corrida["lines"]) == ("Quincenal", 0, [])
        respuesta = empresa.call("POST", "/payroll/runs", {"schedule_id": mundo["jornada"]["id"], "cut_date": "2026-01-20"})
        assert codigo(respuesta, 400) == "invalid_cut_date"
        assert respuesta[1]["detail"] == {"code": "invalid_cut_date", "cut": "2026-01-20", "frequency": "semimonthly"}
        respuesta = empresa.call("POST", "/payroll/runs", {"schedule_id": mundo["jornada"]["id"], "cut_date": "2026-01-15"})
        assert codigo(respuesta, 409) == "run_already_exists"
        assert respuesta[1]["detail"]["run_id"] == corrida["id"]
        assert codigo(empresa.call("POST", "/payroll/runs", {"schedule_id": 99999, "cut_date": "2026-01-15"}), 404) == "schedule_not_found"

    def test_aprobar_sin_calcular_no(self, empresa: Api, corrida: dict):
        assert codigo(empresa.call("POST", f"/payroll/runs/{corrida['id']}/approve"), 409) == "run_not_calculated"

    def test_calcular_congela_cada_rubro(self, empresa: Api, mundo: dict, corrida: dict):
        calculada = empresa.ok("POST", f"/payroll/runs/{corrida['id']}/calculate")
        [linea] = calculada["lines"]
        assert (linea["employee_id"], linea["employee_name"], linea["gross"]) == (mundo["empleada"]["id"], "Ana Mora Solís", 500000)

        tasas = empresa.ok("GET", "/payroll/rates?on=2026-01-15")
        obreras = {t["concept"]: t["value"] for t in tasas["rates"] if t["payer"] == "employee"}
        rubros = {(i["concept"], i["payer"]): i for i in linea["items"]}
        for concepto, tasa in obreras.items():
            rubro = rubros[(concepto, "employee")]
            assert (rubro["base"], rubro["rate"], rubro["amount"]) == (500000, tasa, round(500000 * tasa, 2))
        assert linea["employee_deductions"] == round(sum(round(500000 * t, 2) for t in obreras.values()), 2)
        # La renta de la quincena es la mitad de la del mes proyectado (RN-73), con
        # los tramos vigentes al corte: se calcula con ellos y no con una cifra
        # escrita acá, que vence con el decreto de cada diciembre.
        del_mes = sum(
            max(0, min(1000000, t["upper"] or 1000000) - t["lower"]) * t["rate"] for t in tasas["brackets"]
        )
        assert del_mes > 0
        assert linea["income_tax"] == round(del_mes / 2, 2)
        assert rubros[("deduction", "employee")]["amount"] == 10000
        assert linea["other_deductions"] == 10000
        assert linea["net"] == round(linea["gross"] - linea["employee_deductions"] - linea["income_tax"] - 10000, 2)
        assert rubros[("rt", "employer")]["rate"] == 0.0146
        assert calculada["status"] == "draft"

    def test_sin_tasas_a_la_fecha_no_se_calcula(self, empresa: Api, mundo: dict):
        vieja = empresa.ok("POST", "/payroll/runs", {"schedule_id": mundo["jornada"]["id"], "cut_date": "2025-12-31"})
        respuesta = empresa.call("POST", f"/payroll/runs/{vieja['id']}/calculate")
        assert codigo(respuesta, 409) == "rates_missing_for_date"
        assert respuesta[1]["detail"]["on"] == "2025-12-31" and "ivm:employee" in respuesta[1]["detail"]["missing"]

    def test_aprobar_y_pagar_dejan_fecha_asiento_y_bitacora(self, empresa: Api, soporte: Api, corrida: dict):
        assert codigo(empresa.call("POST", f"/payroll/runs/{corrida['id']}/pay"), 409) == "run_not_approved"
        aprobada = empresa.ok("POST", f"/payroll/runs/{corrida['id']}/approve")
        assert aprobada["status"] == "approved" and aprobada["approved_at"] is not None
        assert codigo(empresa.call("POST", f"/payroll/runs/{corrida['id']}/calculate"), 409) == "run_not_editable"

        pagada = empresa.ok("POST", f"/payroll/runs/{corrida['id']}/pay")
        assert pagada["status"] == "paid" and pagada["paid_at"] is not None
        assert pagada["journal_entry_id"] is not None

        asiento = empresa.ok("GET", f"/accounting/entries/{pagada['journal_entry_id']}")
        cuentas = {c["id"]: c["code"] for c in empresa.ok("GET", "/accounting/accounts")}
        por_cuenta = {cuentas[l["account_id"]]: (l["debit"], l["credit"]) for l in asiento["lines"]}
        [linea] = pagada["lines"]
        assert por_cuenta["6.1.01"] == (linea["gross"], 0)
        assert por_cuenta["6.1.02"] == (linea["employer_charges"], 0)
        assert por_cuenta["2.1.04"] == (0, round(linea["employee_deductions"] + linea["employer_charges"], 2))
        assert por_cuenta["2.1.03"] == (0, linea["income_tax"])
        assert por_cuenta["2.1.06"] == (0, linea["other_deductions"])
        assert por_cuenta["2.1.05"] == (0, linea["net"])
        assert round(sum(d for d, _ in por_cuenta.values()), 2) == round(sum(c for _, c in por_cuenta.values()), 2)

        bitacora = soporte.ok("GET", "/support/audit?accion=planilla_pagada")
        assert any(f"corrida {corrida['id']}" in (l.get("detalle") or "") for l in bitacora["lineas"])

        assert codigo(empresa.call("POST", f"/payroll/runs/{corrida['id']}/pay"), 409) == "run_already_paid"
        assert codigo(empresa.call("POST", f"/payroll/runs/{corrida['id']}/calculate"), 409) == "run_already_paid"
        assert codigo(empresa.call("GET", "/payroll/runs/99999"), 404) == "run_not_found"

    def test_la_jornada_con_corridas_pagadas_no_cambia_de_corte(self, empresa: Api, mundo: dict):
        respuesta = empresa.call("PUT", f"/payroll/schedules/{mundo['jornada']['id']}", {"first_cut_day": 14})
        assert codigo(respuesta, 409) == "schedule_locked"
        # Renombrarla sí.
        assert empresa.ok("PUT", f"/payroll/schedules/{mundo['jornada']['id']}", {"name": "Cajas"})["name"] == "Cajas"

    def test_la_pagada_no_cambia_con_una_tasa_nueva_y_la_siguiente_si(self, empresa: Api, soporte: Api, mundo: dict, corrida: dict):
        """RN-66: la boleta se reimprime de los rubros congelados."""
        antes = empresa.ok("GET", f"/payroll/runs/{corrida['id']}")
        concepto = f"prueba_{marca_unica()}"
        soporte.ok(
            "PUT",
            "/support/payroll/rates",
            {"concept": concepto, "payer": "employer", "value": "0.01", "valid_from": AYER.isoformat(), "source": "Prueba automática, no es una norma"},
        )
        despues = empresa.ok("GET", f"/payroll/runs/{corrida['id']}")
        assert despues["lines"] == antes["lines"]

        corte = proximo_corte_quincenal(HOY)
        nueva = empresa.ok("POST", "/payroll/runs", {"schedule_id": mundo["jornada"]["id"], "cut_date": corte.isoformat()})
        calculada = empresa.ok("POST", f"/payroll/runs/{nueva['id']}/calculate")
        conceptos = {i["concept"] for i in calculada["lines"][0]["items"] if i["payer"] == "employer"}
        assert concepto in conceptos
        assert concepto not in {i["concept"] for i in antes["lines"][0]["items"]}

    def test_la_incapacidad_registrada_despues_de_pagar_entra_en_la_siguiente(self, empresa: Api, mundo: dict):
        empresa.ok(
            "POST",
            "/payroll/actions",
            {"employee_id": mundo["empleada"]["id"], "kind": "sick_leave_ccss", "starts_on": "2026-01-12", "ends_on": "2026-01-17"},
        )
        segunda = empresa.ok("POST", "/payroll/runs", {"schedule_id": mundo["jornada"]["id"], "cut_date": "2026-01-31"})
        calculada = empresa.ok("POST", f"/payroll/runs/{segunda['id']}/calculate")
        tramos = [i for i in calculada["lines"][0]["items"] if i["concept"] == "sick_leave_ccss"]
        assert [(t["applied_from"], t["applied_to"], t["quantity"]) for t in tramos] == [
            ("2026-01-12", "2026-01-15", 4),
            ("2026-01-16", "2026-01-17", 2),
        ]
        historial = empresa.ok("GET", f"/payroll/employees/{mundo['empleada']['id']}/actions")
        deduccion = next(a for a in historial if a["kind"] == "deduction")
        assert deduccion["applied_total"] == 10000 and deduccion["applied"][0]["run_status"] == "paid"
        corridas = empresa.ok("GET", "/payroll/runs")
        assert {c["status"] for c in corridas} >= {"paid", "draft"}


# -------------------------------------------------------------- aislamiento


class TestNoSeVeLaPlanillaDeLaOtra:
    """Con el token de B, lo de A responde 404 en todas las rutas por id."""

    @pytest.fixture(scope="class")
    def propia(self, api: Api) -> dict:
        empresa = compania_propia(api, "aislada")
        jornada = jornada_quincenal(empresa)
        puesto_ = puesto(empresa)
        poliza_ = poliza(empresa)
        empleado = empresa.ok("POST", "/payroll/employees", ficha("405670891"))
        contratar(empresa, empleado["id"], jornada["id"], puesto_["id"], "300000")
        accion = empresa.ok(
            "POST", "/payroll/actions", {"employee_id": empleado["id"], "kind": "bonus", "starts_on": "2026-01-10", "amount": "1000"}
        )
        corrida = empresa.ok("POST", "/payroll/runs", {"schedule_id": jornada["id"], "cut_date": "2026-01-15"})
        return {
            "jornada": jornada["id"],
            "puesto": puesto_["id"],
            "poliza": poliza_["id"],
            "empleado": empleado["id"],
            "accion": accion["id"],
            "corrida": corrida["id"],
        }

    @pytest.fixture(scope="class")
    def ajena(self, api: Api) -> Api:
        return compania_propia(api, "intrusa")

    def test_cada_ruta_por_id(self, ajena: Api, propia: dict):
        rutas = [
            ("PUT", f"/payroll/schedules/{propia['jornada']}", {"name": "x"}),
            ("PUT", f"/payroll/positions/{propia['puesto']}", {"name": "x"}),
            ("PUT", f"/payroll/policies/{propia['poliza']}", {"rt_rate": "0.01"}),
            ("GET", f"/payroll/employees/{propia['empleado']}", None),
            ("PUT", f"/payroll/employees/{propia['empleado']}", {"phone": "1"}),
            ("POST", f"/payroll/employees/{propia['empleado']}/terminate", {"terminated_on": "2026-02-01", "cause": "resignation"}),
            ("GET", f"/payroll/employees/{propia['empleado']}/actions", None),
            ("GET", f"/payroll/contracts?employee={propia['empleado']}", None),
            ("POST", "/payroll/actions", {"employee_id": propia["empleado"], "kind": "bonus", "starts_on": "2026-01-10", "amount": "1"}),
            ("PUT", f"/payroll/actions/{propia['accion']}", {"starts_on": "2026-01-11"}),
            ("POST", f"/payroll/actions/{propia['accion']}/cancel", None),
            ("POST", f"/payroll/actions/{propia['accion']}/suspend", {"reason": "pausa"}),
            ("GET", f"/payroll/runs/{propia['corrida']}", None),
            ("POST", f"/payroll/runs/{propia['corrida']}/calculate", None),
            ("POST", f"/payroll/runs/{propia['corrida']}/approve", None),
            ("POST", f"/payroll/runs/{propia['corrida']}/pay", None),
            ("POST", "/payroll/runs", {"schedule_id": propia["jornada"], "cut_date": "2026-01-15"}),
            ("POST", "/payroll/contracts", {"employee_id": propia["empleado"], "schedule_id": propia["jornada"], "position_id": propia["puesto"], "valid_from": "2026-05-01", "period_salary": "1"}),
        ]
        for metodo, ruta, cuerpo in rutas:
            estado, respuesta = ajena.call(metodo, ruta, cuerpo)
            assert estado == 404, f"{metodo} {ruta} respondió {estado} con el token de otra compañía: {respuesta}"

    def test_las_listas_salen_vacias(self, ajena: Api):
        for ruta in ("/payroll/schedules", "/payroll/positions", "/payroll/policies", "/payroll/employees", "/payroll/runs"):
            assert ajena.ok("GET", ruta) == [], ruta
