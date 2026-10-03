"""Los archivos del mes: INS, CCSS y renta retenida (RN-96, T-1211, T-1219).

El trazado del INS que se comprueba acá es el de `docs/ins/README.md` (V08D):
posiciones y anchos fijos. Las cifras son inventadas; lo que se prueba es que
cada campo caiga donde tiene que caer.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.errors import ExportDataIncomplete
from app.domain.money import Money
from app.domain.payroll import EARNING, EMPLOYEE, PayItem
from app.domain.payroll_calendar import Period
from app.domain.payroll_files import (
    EXCLUSION,
    INCLUSION,
    LEAVE_PAID,
    LEAVE_UNPAID,
    OCCUPATION_CHANGE,
    SICK_LEAVE_SEM,
    Employer,
    Movement,
    WorkerAction,
    WorkerMonth,
    ccss_identification,
    ccss_movements,
    ccss_report,
    ccss_shift,
    check_complete,
    days_paid,
    earned,
    income_tax_report,
    ins_days_and_hours,
    ins_file,
    ins_header,
    ins_observation,
    ins_policy_number,
    ins_record,
    ins_shift,
    missing_for_ccss,
    missing_for_ins,
    month_period,
    withheld,
)
from app.domain.payroll_actions import CONTRIBUTORY, TAXABLE

D = Decimal
ENERO = month_period(2026, 1)

PATRONO = Employer(
    identification_type="02",
    identification="3-101-123456",
    employer_number="2-03101123456-001-001",
    phone="2222-3333",
    email="planilla@ejemplo.test",
    address="Barrio Ejemplo, San José",
)


def rubro(concept, amount, *, payer=EARNING, quantity=None, desde=None, hasta=None, action_id=None, base=None):
    return PayItem(
        concept,
        payer,
        Money(base if base is not None else amount),
        None,
        Money(amount),
        action_id=action_id,
        quantity=quantity,
        applied_from=desde,
        applied_to=hasta,
    )


BASE_ENERO = (
    rubro("base", 300000, quantity=D(15), desde=date(2026, 1, 1), hasta=date(2026, 1, 15)),
    rubro("base", 300000, quantity=D(15), desde=date(2026, 1, 16), hasta=date(2026, 1, 31)),
    rubro("sem", 33000, payer=EMPLOYEE),
    rubro("income_tax", 5000, payer=EMPLOYEE),
    rubro("income_tax", 5000, payer=EMPLOYEE),
)


def trabajadora(**cambios) -> WorkerMonth:
    datos = dict(
        employee_id=1,
        identification_type="national",
        identification="12345678",
        insured_number=None,
        first_name="Ana María",
        last_name_1="Mora",
        last_name_2="Solís",
        hired_on=date(2025, 6, 1),
        terminated_on=None,
        termination_cause=None,
        ccss_code="4211",
        ins_code="52",
        policy_id=9,
        policy_number="RT-727900",
        shift="day",
        hours_per_day=D(8),
        items=BASE_ENERO,
        actions=(),
    )
    datos.update(cambios)
    return WorkerMonth(**datos)


class TestLoQueFalta:
    def test_el_mes(self):
        assert month_period(2026, 2) == Period(date(2026, 2, 1), date(2026, 2, 28))

    def test_a_la_extranjera_le_falta_el_asegurado_y_a_todos_los_codigos(self):
        assert missing_for_ccss(trabajadora()) == ()
        assert missing_for_ccss(trabajadora(identification_type="dimex", ccss_code=None)) == ("insured_number", "ccss_code")
        assert missing_for_ins(trabajadora(identification_type="passport", ins_code=None, policy_id=None)) == (
            "insured_number",
            "ins_code",
            "policy",
        )

    def test_se_junta_todo_antes_de_fallar(self):
        with pytest.raises(ExportDataIncomplete) as e:
            check_complete(
                [trabajadora(ccss_code=None), trabajadora(employee_id=2), trabajadora(employee_id=3, identification_type="dimex")],
                per_worker=missing_for_ccss,
                company=(("employer_number", None), ("identification", "3-101")),
            )
        assert e.value.missing == ((1, ("ccss_code",)), (3, ("insured_number",)))
        assert e.value.company == ("employer_number",)
        check_complete([trabajadora()], per_worker=missing_for_ccss, company=(("employer_number", "1"),))


class TestLasSumas:
    def test_lo_devengado_los_dias_y_lo_retenido(self):
        w = trabajadora(items=BASE_ENERO + (rubro("sick_leave_subsidy", 10000), rubro("overtime", 15000)))
        assert earned(w.items, CONTRIBUTORY) == Money(615000)
        assert earned(w.items, TAXABLE) == Money(615000)
        assert days_paid(w.items) == 30
        assert withheld(w.items) == Money(10000)


class TestElInformeDeLaCcss:
    def test_la_identificacion_como_la_pide_el_formulario(self):
        assert ccss_identification(trabajadora()) == "012345678"
        assert ccss_identification(trabajadora(identification_type="dimex", identification="155812345678", insured_number="2600018904")) == "2600018904"
        assert ccss_identification(trabajadora(identification_type="passport", identification="AB123")) == "AB123"

    def test_la_jornada(self):
        assert ccss_shift(trabajadora()) == "diurna"
        assert ccss_shift(trabajadora(shift="mixed")) == "mixta"
        assert ccss_shift(trabajadora(shift="night", hours_per_day=D(6))) == "nocturna"
        assert ccss_shift(trabajadora(hours_per_day=D(4))) == "parcial"
        assert ccss_shift(trabajadora(shift="otra")) == "diurna"

    def test_los_movimientos_con_sus_fechas(self):
        w = trabajadora(
            hired_on=date(2026, 1, 6),
            terminated_on=date(2026, 1, 28),
            termination_cause="resignation",
            items=BASE_ENERO
            + (
                rubro("sick_leave_ccss", -40000, quantity=D(2), desde=date(2026, 1, 14), hasta=date(2026, 1, 15), action_id=5),
                rubro("sick_leave_subsidy", 20000, quantity=D(2), desde=date(2026, 1, 14), hasta=date(2026, 1, 15), action_id=5),
                rubro("sick_leave_ccss", -60000, quantity=D(3), desde=date(2026, 1, 16), hasta=date(2026, 1, 18), action_id=5),
                rubro("paid_leave", 0, quantity=D(1), desde=date(2026, 1, 20), hasta=date(2026, 1, 20), action_id=6),
                rubro("unpaid_leave", -20000, quantity=D(1), desde=date(2026, 1, 21), hasta=date(2026, 1, 21), action_id=7),
                rubro("maternity", -20000, quantity=D(1), desde=date(2026, 1, 22), hasta=date(2026, 1, 22), action_id=8),
                rubro("sick_leave_ins", -20000, quantity=D(1), desde=date(2026, 1, 23), hasta=date(2026, 1, 23), action_id=9),
                rubro("overtime", 15000, quantity=D(4), desde=date(2026, 1, 10), hasta=date(2026, 1, 10), action_id=10),
                rubro("sick_leave_ccss", 0, action_id=11),
            ),
            actions=(
                WorkerAction("position_change", date(2026, 1, 15), new_ccss_code="4212"),
                WorkerAction("position_change", date(2025, 12, 15), new_ccss_code="4213"),
                WorkerAction("bonus", date(2026, 1, 15)),
            ),
        )
        assert ccss_movements(w, ENERO) == (
            Movement(INCLUSION, date(2026, 1, 6)),
            Movement(SICK_LEAVE_SEM, date(2026, 1, 14), date(2026, 1, 18)),
            Movement(OCCUPATION_CHANGE, date(2026, 1, 15), detail="4212"),
            Movement(LEAVE_PAID, date(2026, 1, 20), date(2026, 1, 20)),
            Movement(LEAVE_UNPAID, date(2026, 1, 21), date(2026, 1, 21)),
            Movement("maternity", date(2026, 1, 22), date(2026, 1, 22)),
            Movement("sick_leave_ins", date(2026, 1, 23), date(2026, 1, 23)),
            Movement(EXCLUSION, date(2026, 1, 28), detail="resignation"),
        )

    def test_el_informe_ordena_suma_y_exige_el_numero_patronal(self):
        informe = ccss_report(PATRONO, [trabajadora(employee_id=2, last_name_1="Zamora"), trabajadora()], ENERO)
        assert [r.employee_id for r in informe.rows] == [1, 2]
        fila = informe.rows[0]
        assert (fila.identification, fila.full_name, fila.ccss_code, fila.shift, fila.salary, fila.days) == (
            "012345678",
            "Ana María Mora Solís",
            "4211",
            "diurna",
            Money(600000),
            30,
        )
        assert (informe.employer_number, informe.period, informe.total_salary) == (PATRONO.employer_number, ENERO, Money(1200000))
        with pytest.raises(ExportDataIncomplete) as e:
            ccss_report(Employer("02", "3-101", None, None, None, None), [trabajadora()], ENERO)
        assert e.value.company == ("employer_number",)


class TestLaRentaRetenida:
    def test_suma_lo_gravable_y_lo_retenido_por_empleado(self):
        informe = income_tax_report([trabajadora(employee_id=2, last_name_1="Zamora"), trabajadora()], ENERO)
        assert [(r.employee_id, r.taxable, r.withheld) for r in informe.rows] == [
            (1, Money(600000), Money(10000)),
            (2, Money(600000), Money(10000)),
        ]
        assert (informe.total_taxable, informe.total_withheld) == (Money(1200000), Money(20000))


class TestElArchivoDelIns:
    def test_la_poliza_a_siete_digitos(self):
        assert ins_policy_number("RT-727900") == "0727900"
        assert ins_policy_number("12345678") == "2345678"
        assert ins_policy_number(None) == "0000000"

    def test_la_jornada_y_los_dias(self):
        assert ins_shift(trabajadora()) == "01"
        assert ins_shift(trabajadora(hours_per_day=D(4))) == "02"
        assert ins_days_and_hours(trabajadora()) == (30, 240)
        # Un mes de 31 días en una semanal paga 31; más de 31 no existe.
        muchos = trabajadora(items=(rubro("base", 1, quantity=D("33.5")),), hours_per_day=D("7.5"))
        assert ins_days_and_hours(muchos) == (31, 233)

    def test_la_observacion_que_mas_pesa(self):
        assert ins_observation(trabajadora(), ENERO) == "00"
        assert ins_observation(trabajadora(hired_on=date(2026, 1, 6)), ENERO) == "01"
        assert ins_observation(trabajadora(terminated_on=date(2026, 1, 20)), ENERO) == "02"
        assert ins_observation(trabajadora(hired_on=date(2026, 1, 6), terminated_on=date(2026, 1, 20)), ENERO) == "05"
        con = lambda concepto: trabajadora(items=BASE_ENERO + (rubro(concepto, -1, quantity=D(1), desde=date(2026, 1, 5), hasta=date(2026, 1, 5), action_id=1),))
        assert ins_observation(con("maternity"), ENERO) == "07"
        assert ins_observation(con("sick_leave_ccss"), ENERO) == "03"
        assert ins_observation(con("sick_leave_ins"), ENERO) == "04"
        assert ins_observation(con("unpaid_leave"), ENERO) == "06"

    def test_el_registro_cae_en_sus_posiciones(self):
        linea = ins_record(trabajadora(), ENERO)
        assert len(linea) == 114
        assert linea[0] == "0"
        assert linea[1:20] == "12345678".ljust(19)
        assert linea[20:40] == " " * 20  # el asegurado de una nacional no va
        assert linea[40:55] == "ANA MARÍA".ljust(15)
        assert linea[55:70] == "MORA".ljust(15)
        assert linea[70:85] == "SOLÍS".ljust(15)
        assert linea[85:98] == "0000600000.00"
        assert (linea[98:101], linea[101:105], linea[105:107], linea[107:109], linea[109], linea[110:114]) == (
            "030",
            "0240",
            "01",
            "00",
            "0",
            "0052",
        )

    def test_la_extranjera_lleva_su_asegurado_y_los_nombres_largos_se_cortan(self):
        w = trabajadora(
            identification_type="dimex",
            identification="155812345678",
            insured_number="2600018904",
            first_name="Maria de los Angeles del Carmen",
            last_name_2=None,
            ins_code="A1",
            items=(rubro("base", -5),),
        )
        linea = ins_record(w, ENERO)
        assert linea[0] == "6"
        assert linea[20:40] == "2600018904".ljust(20)
        assert linea[40:55] == "MARIA DE LOS AN"
        assert linea[70:85] == "...".ljust(15)
        assert linea[85:98] == "0000000000.00"
        assert linea[110:114] == "0001"
        assert ins_record(trabajadora(identification_type="passport"), ENERO)[0] == "9"
        assert ins_record(trabajadora(identification_type="work_permit"), ENERO)[0] == "8"
        assert ins_record(trabajadora(identification_type="otro"), ENERO)[0] == "0"

    def test_el_encabezado(self):
        primera, correo, domicilio = ins_header(PATRONO, "727900", ENERO)
        assert primera == "0727900M202601 " + "23101123456".ljust(20) + "22223333" + "00000000" + " V08D"
        assert len(primera) == 56
        assert correo == "Email " + "planilla@ejemplo.test".ljust(50)
        assert domicilio == "Domicilio " + "BARRIO EJEMPLO, SAN JOSÉ".ljust(171)
        sin_datos = ins_header(Employer(None, None, None, None, None, None), "1", ENERO)[0]
        assert sin_datos.startswith("0000001M202601 0" + " " * 19 + "00000000")

    def test_el_archivo_entero(self):
        archivo = ins_file(PATRONO, "727900", [trabajadora(employee_id=2, last_name_1="Zamora"), trabajadora()], ENERO)
        assert archivo.filename == "PL0727900M202601-V08D (Texto).txt"
        lineas = archivo.content.split("\r\n")
        assert archivo.content.endswith("\r\n") and lineas[-1] == ""
        assert len(lineas) == 6
        assert lineas[3][55:70] == "MORA".ljust(15)
        assert lineas[4][55:70] == "ZAMORA".ljust(15)
        assert archivo.encoded.decode("iso-8859-1") == archivo.content
        # Un carácter que latin-1 no tiene no tumba el archivo.
        rara = ins_file(PATRONO, "727900", [trabajadora(first_name="Zoë ✓")], ENERO)
        assert b"?" in rara.encoded

    def test_lo_que_falta_para_el_ins(self):
        with pytest.raises(ExportDataIncomplete) as e:
            ins_file(Employer("02", None, None, None, None, None), "RT", [trabajadora(policy_id=None)], ENERO)
        assert e.value.missing == ((1, ("policy",)),)
        assert e.value.company == ("identification", "policy_number")
