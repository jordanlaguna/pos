"""Los archivos del mes por la aplicación (RN-96, T-1211, T-1219).

El trazado y las sumas están probados en el dominio; acá, que cada caso de uso
pida el mes que le toca, filtre por póliza y deje pasar lo que falta.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.application.use_cases.payroll_exports import (
    ExportCcssReport,
    ExportInsFile,
    IncomeTaxSummary,
    PolicyNotFound,
)
from app.domain.errors import ExportDataIncomplete
from app.domain.money import Money
from app.domain.payroll import EARNING, EMPLOYEE, PayItem
from app.domain.payroll_calendar import Period
from app.domain.payroll_files import Employer, WorkerMonth

from .fakes_payroll import FakePayrollReports

D = Decimal
PATRONO = Employer("02", "3101123456", "203101123456001001", "22223333", "p@ejemplo.test", "San José")


def trabajador(employee_id: int, policy_id: int = 9, **cambios) -> WorkerMonth:
    datos = dict(
        employee_id=employee_id,
        identification_type="national",
        identification=f"10{employee_id:07d}",
        insured_number=None,
        first_name="Ana",
        last_name_1=f"Mora{employee_id}",
        last_name_2=None,
        hired_on=date(2025, 1, 1),
        terminated_on=None,
        termination_cause=None,
        ccss_code="4211",
        ins_code="52",
        policy_id=policy_id,
        policy_number="727900" if policy_id == 9 else "100",
        shift="day",
        hours_per_day=D(8),
        items=(
            PayItem("base", EARNING, Money(600000), None, Money(600000), quantity=D(30), applied_from=date(2026, 1, 1), applied_to=date(2026, 1, 31)),
            PayItem("income_tax", EMPLOYEE, Money(600000), None, Money(10000)),
        ),
        actions=(),
    )
    datos.update(cambios)
    return WorkerMonth(**datos)


def informes(**cambios) -> FakePayrollReports:
    datos = dict(workers=[trabajador(1), trabajador(2, policy_id=10)], employer=PATRONO, policies={9: "727900", 10: "100"})
    datos.update(cambios)
    return FakePayrollReports(**datos)


class TestLosArchivosDelMes:
    def test_el_informe_de_la_ccss_es_del_mes_que_se_pide(self):
        reportes = informes()
        informe = ExportCcssReport(reports=reportes)(2026, 1)
        assert reportes.pedidos == [(2026, 1)]
        assert (informe.period, [r.employee_id for r in informe.rows], informe.total_salary) == (
            Period(date(2026, 1, 1), date(2026, 1, 31)),
            [1, 2],
            Money(1200000),
        )

    def test_el_archivo_del_ins_es_de_una_poliza(self):
        archivo = ExportInsFile(reports=informes())(2026, 1, 9)
        assert archivo.filename == "PL0727900M202601-V08D (Texto).txt"
        lineas = archivo.content.split("\r\n")
        assert len(lineas) == 5  # tres de encabezado, un trabajador, el salto final
        assert "MORA1" in lineas[3] and "MORA2" not in archivo.content
        with pytest.raises(PolicyNotFound):
            ExportInsFile(reports=informes())(2026, 1, 77)

    def test_lo_que_falta_pasa_entero(self):
        with pytest.raises(ExportDataIncomplete) as e:
            ExportInsFile(reports=informes(workers=[trabajador(1, ins_code=None)]))(2026, 1, 9)
        assert e.value.missing == ((1, ("ins_code",)),)

    def test_la_renta_retenida(self):
        resumen = IncomeTaxSummary(reports=informes())(2026, 1)
        assert (resumen.total_taxable, resumen.total_withheld) == (Money(1200000), Money(20000))
