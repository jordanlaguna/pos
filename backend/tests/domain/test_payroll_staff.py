"""Empleados, contratos, puestos y pólizas (RN-72, RN-94, RN-95, T-1205, T-1217)."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.errors import InvalidContract, InvalidEmployee, InvalidPayrollSettings
from app.domain.money import Money
from app.domain.payroll_staff import (
    GENDERS,
    IDENTIFICATION_TYPES,
    MARITAL_STATUSES,
    ContractData,
    EmployeeData,
    check_contract,
    check_employee,
    check_policy,
    check_position,
    check_termination,
    clean_employer_number,
)

INGRESO = date(2026, 3, 1)


def empleada(**cambios) -> EmployeeData:
    datos = dict(
        identification_type="national",
        identification="102340567",
        first_name="Ana",
        last_name_1="Mora",
        birth_date=date(1990, 5, 20),
        gender="F",
        marital_status="single",
        nationality="CR",
        hired_on=INGRESO,
    )
    datos.update(cambios)
    return EmployeeData(**datos)


def campo_y_motivo(excepcion) -> tuple[str, str]:
    return excepcion.value.field, excepcion.value.reason


class TestElEmpleado:
    def test_una_ficha_completa_pasa(self):
        check_employee(empleada())
        check_employee(empleada(identification_type="passport", identification="AB123456", last_name_2=None))

    def test_las_listas_son_cerradas(self):
        assert len(IDENTIFICATION_TYPES) == 5
        assert GENDERS == ("F", "M")
        assert "free_union" in MARITAL_STATUSES

    @pytest.mark.parametrize(
        "cambio, esperado",
        [
            ({"identification_type": "cedula"}, ("identification_type", "unknown")),
            ({"identification": "  "}, ("identification", "required")),
            ({"identification": "1" * 31}, ("identification", "too_long")),
            ({"identification": "1-0234-0567"}, ("identification", "not_digits")),
            ({"first_name": " "}, ("first_name", "required")),
            ({"last_name_1": ""}, ("last_name_1", "required")),
            ({"birth_date": date(2027, 1, 1)}, ("birth_date", "in_the_future")),
            ({"birth_date": date(2012, 3, 2)}, ("birth_date", "too_young")),
            ({"gender": "X"}, ("gender", "unknown")),
            ({"marital_status": "soltera"}, ("marital_status", "unknown")),
            ({"nationality": "Costa Rica"}, ("nationality", "bad_format")),
            ({"email": "ana.mora"}, ("email", "bad_format")),
            ({"iban": "12345"}, ("iban", "bad_format")),
            ({"dependent_children": -1}, ("dependent_children", "negative")),
        ],
    )
    def test_cada_dato_malo_dice_cual_y_por_que(self, cambio, esperado):
        with pytest.raises(InvalidEmployee) as e:
            check_employee(empleada(**cambio))
        assert campo_y_motivo(e) == esperado

    def test_quince_anos_justos_el_dia_del_ingreso_entran(self):
        # El Código de la Niñez permite trabajar desde los quince.
        check_employee(empleada(birth_date=date(2011, 3, 1)))

    def test_el_pasaporte_puede_llevar_letras_y_el_dimex_no(self):
        check_employee(empleada(identification_type="passport", identification="X9Z12"))
        with pytest.raises(InvalidEmployee):
            check_employee(empleada(identification_type="dimex", identification="X9Z12"))

    def test_el_correo_y_el_iban_vacios_valen(self):
        check_employee(empleada(email="  ", iban=""))
        check_employee(empleada(iban="CR05 0152 0200 1026 2840 66"))


class TestLaBaja:
    def test_una_causa_de_la_lista_y_una_fecha_posterior_al_ingreso(self):
        check_termination(INGRESO, date(2026, 9, 30), "resignation")

    def test_una_causa_inventada(self):
        with pytest.raises(InvalidEmployee) as e:
            check_termination(INGRESO, date(2026, 9, 30), "se_fue")
        assert campo_y_motivo(e) == ("termination_cause", "unknown")

    def test_antes_del_ingreso_no(self):
        with pytest.raises(InvalidEmployee) as e:
            check_termination(INGRESO, date(2026, 2, 28), "resignation")
        assert campo_y_motivo(e) == ("terminated_on", "before_hire")


def contrato(**cambios) -> ContractData:
    datos = dict(valid_from=INGRESO, period_salary=Money(300000), solidarista_rate=None)
    datos.update(cambios)
    return ContractData(**datos)


def revisar(data: ContractData, **cambios) -> None:
    opciones = dict(hired_on=INGRESO, previous_from=None, schedule_active=True, position_active=True)
    opciones.update(cambios)
    check_contract(data, **opciones)


class TestElContrato:
    def test_el_primero_y_un_aumento_despues(self):
        revisar(contrato())
        revisar(contrato(valid_from=date(2026, 7, 1), solidarista_rate=Decimal("0.05")), previous_from=INGRESO)

    @pytest.mark.parametrize(
        "cambio, opciones, esperado",
        [
            ({"period_salary": Money(0)}, {}, ("period_salary", "not_positive")),
            ({"valid_from": date(2026, 2, 1)}, {}, ("valid_from", "before_hire")),
            ({"valid_from": INGRESO}, {"previous_from": INGRESO}, ("valid_from", "overlaps")),
            ({"solidarista_rate": Decimal("5")}, {}, ("solidarista_rate", "out_of_range")),
            ({}, {"schedule_active": False}, ("schedule_id", "inactive")),
            ({}, {"position_active": False}, ("position_id", "inactive")),
        ],
    )
    def test_lo_que_no_entra(self, cambio, opciones, esperado):
        with pytest.raises(InvalidContract) as e:
            revisar(contrato(**cambio), **opciones)
        assert campo_y_motivo(e) == esperado


class TestElPuesto:
    def test_cuatro_digitos_y_hasta_cinco_caracteres(self):
        check_position("Cajera", "4211", "52")
        check_position("Bodeguero", "9333", "AB123")

    @pytest.mark.parametrize(
        "nombre, ccss, ins, esperado",
        [
            ("  ", "4211", "52", ("name", "required")),
            ("Cajera", "421", "52", ("ccss_code", "bad_format")),
            ("Cajera", "42A1", "52", ("ccss_code", "bad_format")),
            ("Cajera", "4211", "", ("ins_code", "bad_format")),
            ("Cajera", "4211", "123456", ("ins_code", "bad_format")),
        ],
    )
    def test_los_codigos_van_como_los_piden_los_archivos(self, nombre, ccss, ins, esperado):
        with pytest.raises(InvalidPayrollSettings) as e:
            check_position(nombre, ccss, ins)
        assert campo_y_motivo(e) == esperado


class TestLaPoliza:
    def test_numero_y_prima(self):
        check_policy("RT-123456", Decimal("0.0146"))

    @pytest.mark.parametrize(
        "numero, prima, esperado",
        [
            (" ", Decimal("0.01"), ("number", "required")),
            ("1" * 21, Decimal("0.01"), ("number", "too_long")),
            ("RT-1", Decimal(0), ("rt_rate", "out_of_range")),
            ("RT-1", Decimal("1.46"), ("rt_rate", "out_of_range")),
        ],
    )
    def test_lo_que_no_entra(self, numero, prima, esperado):
        with pytest.raises(InvalidPayrollSettings) as e:
            check_policy(numero, prima)
        assert campo_y_motivo(e) == esperado


class TestElNumeroPatronal:
    def test_vacio_es_todavia_no_lo_tengo(self):
        assert clean_employer_number(None) is None
        assert clean_employer_number("   ") is None

    def test_digitos_con_o_sin_guiones(self):
        assert clean_employer_number(" 2-03101702934-001-001 ") == "2-03101702934-001-001"
        assert clean_employer_number(203101702934) == "203101702934"

    @pytest.mark.parametrize(
        "valor, motivo",
        [("2 03101702934", "bad_format"), ("12345678", "too_short"), ("1" * 26, "too_long")],
    )
    def test_lo_que_no_es_un_numero_patronal(self, valor, motivo):
        with pytest.raises(InvalidPayrollSettings) as e:
            clean_employer_number(valor)
        assert campo_y_motivo(e) == ("employer_number", motivo)
