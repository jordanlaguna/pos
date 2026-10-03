"""Importar la planilla de otro sistema (RN-97, RF-86, T-1220).

Se prueba lo que la ruta promete: el ensayo señala cada fila mala con el mismo
código que daría el formulario y no escribe nada; sin ensayo, o entra todo o no
entra nada; y lo que entra queda como de apertura, con su fecha.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.application.use_cases.payroll_import import (
    DeductionRow,
    EarningRow,
    EmployeeRow,
    ImportHasErrors,
    ImportPayroll,
    ImportRequest,
    PositionRow,
    RowError,
)
from app.domain.money import Money

from .fakes import FakeUnitOfWork
from .fakes_payroll import (
    FakeActionRepository,
    FakeEmployeeRepository,
    FakeImportRepository,
    FakeOpeningRepository,
    FakeVacationRepository,
    FilaDeJornada,
    RelojFijo,
)

D = Decimal
AHORA = datetime(2026, 2, 1, 8, 0)
CORTE = date(2026, 1, 31)
USUARIO = 7


def empleada(row: int = 2, **cambios) -> EmployeeRow:
    datos = dict(
        identification_type="national",
        identification="102340567",
        first_name="Ana",
        last_name_1="Mora",
        birth_date=date(1990, 5, 20),
        gender="F",
        marital_status="single",
        nationality="CR",
        hired_on=date(2024, 3, 1),
        schedule="Quincenal",
        position="Cajera",
        period_salary=Money(300000),
        vacation_days=D("5.5"),
    )
    datos.update(cambios)
    return EmployeeRow(row=row, **datos)


def pedido(**cambios) -> ImportRequest:
    datos = dict(
        as_of=CORTE,
        positions=(PositionRow(2, "Cajera", "4211", "52"),),
        employees=(empleada(),),
        earnings=(
            EarningRow(2, "102340567", date(2025, 12, 1), Money(600000)),
            EarningRow(3, "102340567", date(2026, 1, 15), Money(610000)),
        ),
        deductions=(DeductionRow(2, "102340567", "deduction", Money(25000), date(2026, 2, 1), balance=Money(150000), memo="Préstamo"),),
    )
    datos.update(cambios)
    return ImportRequest(**datos)


class Mundo:
    def __init__(self, **catalogo):
        base = dict(
            puestos={"Bodega": (1, True), "Vieja": (2, False)},
            jornadas=[FilaDeJornada(1, "Quincenal", "semimonthly", first_cut_day=15), FilaDeJornada(2, "Cerrada", "monthly", is_active=False)],
            polizas={"RT-1": 9},
            empleados={"999999999": 44},
        )
        base.update(catalogo)
        self.catalogo = FakeImportRepository(**base)
        self.empleados = FakeEmployeeRepository()
        self.acciones = FakeActionRepository()
        self.vacaciones = FakeVacationRepository()
        self.apertura = FakeOpeningRepository()
        self.uow = FakeUnitOfWork()

    def importar(self, request: ImportRequest, *, dry_run: bool):
        return ImportPayroll(
            catalog=self.catalogo,
            employees=self.empleados,
            actions=self.acciones,
            vacations=self.vacaciones,
            opening=self.apertura,
            uow=self.uow,
            clock=RelojFijo(AHORA),
        )(request, dry_run=dry_run, user_id=USUARIO)

    def nada_escrito(self) -> bool:
        return not (
            self.catalogo.puestos_nuevos
            or self.catalogo.empleados_nuevos
            or self.empleados.contratos
            or self.vacaciones.movimientos
            or self.apertura.agregados
            or self.acciones.acciones
        )


def errores(resultado) -> list[tuple]:
    return [(e.sheet, e.row, e.code, e.field, e.reason) for e in resultado.errors]


class TestElEnsayo:
    def test_un_archivo_bueno_pasa_y_no_escribe_nada(self):
        mundo = Mundo()
        resultado = mundo.importar(pedido(), dry_run=True)
        assert resultado.ok and resultado.dry_run
        assert (resultado.positions, resultado.employees, resultado.earnings, resultado.deductions) == (1, 1, 2, 1)
        assert mundo.nada_escrito()

    def test_la_fila_mala_sale_con_su_codigo_y_las_demas_siguen(self):
        mundo = Mundo()
        resultado = mundo.importar(
            pedido(employees=(empleada(), empleada(3, identification="1-0234-0568"), empleada(4, identification="302340569"))),
            dry_run=True,
        )
        assert errores(resultado) == [("employees", 3, "invalid_employee", "identification", "not_digits")]
        assert resultado.employees == 3
        assert mundo.nada_escrito()

    def test_lo_que_no_entra_de_un_empleado(self):
        mundo = Mundo()
        resultado = mundo.importar(
            pedido(
                positions=(),
                employees=(
                    empleada(2, identification="999999999"),  # ya existe
                    empleada(3, identification="111111111", position="Bodega"),
                    empleada(4, identification="111111111", position="Bodega"),  # repetida en el archivo
                    empleada(5, identification="222222222", vacation_days=D(-1)),
                    empleada(6, identification="333333333", schedule="Nocturna"),
                    empleada(7, identification="444444444", position="Gerencia"),
                    empleada(8, identification="555555555", position="Bodega", policy="RT-9"),
                    empleada(9, identification="666666666", position="Bodega", period_salary=Money(0)),
                    empleada(10, identification="777777777", position="Vieja"),
                    empleada(11, identification="888888888", position="Bodega", schedule="Cerrada"),
                ),
                earnings=(),
                deductions=(),
            ),
            dry_run=True,
        )
        assert errores(resultado) == [
            ("employees", 2, "employee_identification_taken", "identification", "duplicate"),
            ("employees", 4, "employee_identification_taken", "identification", "duplicate"),
            ("employees", 5, "invalid_employee", "vacation_days", "negative"),
            ("employees", 6, "schedule_not_found", "schedule", None),
            ("employees", 7, "position_not_found", "position", None),
            ("employees", 8, "policy_not_found", "policy", None),
            ("employees", 9, "invalid_contract", "period_salary", "not_positive"),
            ("employees", 10, "invalid_contract", "position_id", "inactive"),
            ("employees", 11, "invalid_contract", "schedule_id", "inactive"),
        ]

    def test_lo_que_no_entra_de_un_puesto_un_mes_o_una_deduccion(self):
        mundo = Mundo()
        resultado = mundo.importar(
            pedido(
                positions=(PositionRow(2, "Cajera", "4211", "52"), PositionRow(3, "Chofer", "42", "52"), PositionRow(4, "Cajera", "4211", "52")),
                earnings=(
                    EarningRow(2, "000000000", date(2025, 12, 1), Money(1)),
                    EarningRow(3, "102340567", date(2025, 12, 1), Money(-1)),
                    EarningRow(4, "102340567", date(2025, 11, 5), Money(1)),
                    EarningRow(5, "102340567", date(2025, 11, 20), Money(1)),
                ),
                deductions=(
                    DeductionRow(2, "000000000", "deduction", Money(1), date(2026, 2, 1)),
                    DeductionRow(3, "102340567", "bonus", Money(1), date(2026, 2, 1)),
                    DeductionRow(4, "102340567", "garnishment", Money(1), date(2026, 2, 1)),
                    DeductionRow(5, "102340567", "deduction", Money(0), date(2026, 2, 1)),
                ),
            ),
            dry_run=True,
        )
        assert errores(resultado) == [
            ("positions", 3, "invalid_payroll_settings", "ccss_code", "bad_format"),
            ("positions", 4, "payroll_name_taken", "name", "duplicate"),
            ("earnings", 2, "employee_not_found", "identification", None),
            ("earnings", 3, "invalid_employee", "gross", "negative"),
            ("earnings", 5, "invalid_employee", "month", "duplicate"),
            ("deductions", 2, "employee_not_found", "identification", None),
            ("deductions", 3, "invalid_action", "kind", "unknown"),
            ("deductions", 4, "invalid_action", "total_amount", "required"),
            ("deductions", 5, "invalid_action", "amount", "not_positive"),
        ]


class TestLaEscritura:
    def test_entra_entero_y_queda_como_de_apertura(self):
        mundo = Mundo()
        resultado = mundo.importar(pedido(), dry_run=False)
        assert resultado.ok and not resultado.dry_run

        [puesto] = mundo.catalogo.puestos_nuevos
        assert (puesto["name"], puesto["ccss_code"]) == ("Cajera", "4211")
        [empleada_] = mundo.catalogo.empleados_nuevos
        assert (empleada_["identification"], empleada_["first_name"], empleada_["hired_on"]) == ("102340567", "Ana", date(2024, 3, 1))
        [contrato] = mundo.empleados.contratos
        assert (contrato.employee_id, contrato.schedule_id, contrato.position_id, contrato.valid_from, contrato.period_salary) == (
            empleada_["id"],
            1,
            puesto["id"],
            date(2024, 3, 1),
            D(300000),
        )
        [vacaciones] = mundo.vacaciones.movimientos
        assert (vacaciones.kind, vacaciones.days, vacaciones.on_date) == ("opening", D("5.5"), CORTE)
        assert [(m[1], m[2], m[3], m[4]) for m in mundo.apertura.agregados] == [
            (date(2025, 12, 1), Money(600000), USUARIO, AHORA),
            (date(2026, 1, 1), Money(610000), USUARIO, AHORA),
        ]
        [prestamo] = mundo.acciones.acciones
        assert (prestamo.kind, prestamo.amount, prestamo.total_amount, prestamo.is_recurring, prestamo.source, prestamo.memo) == (
            "deduction",
            D(25000),
            D(150000),
            True,
            "import",
            "Préstamo",
        )
        assert (prestamo.created_by, prestamo.created_at) == (USUARIO, AHORA)
        assert mundo.uow.committed

    def test_el_puesto_que_ya_existe_se_reutiliza_y_la_poliza_y_el_contrato_propio(self):
        mundo = Mundo()
        mundo.importar(
            pedido(
                positions=(PositionRow(2, "Bodega", "4211", "52"),),
                employees=(empleada(position="Bodega", policy="RT-1", contract_from=date(2025, 1, 1), vacation_days=None, solidarista_rate=D("0.03")),),
                earnings=(),
                deductions=(DeductionRow(2, "102340567", "garnishment", Money(10000), date(2026, 2, 1), balance=Money(90000), is_recurring=True),),
            ),
            dry_run=False,
        )
        assert mundo.catalogo.puestos_nuevos == []
        [contrato] = mundo.empleados.contratos
        assert (contrato.position_id, contrato.ins_policy_id, contrato.valid_from, contrato.solidarista_rate) == (1, 9, date(2025, 1, 1), D("0.03"))
        assert mundo.vacaciones.movimientos == []
        [embargo] = mundo.acciones.acciones
        # Un embargo no es recurrente por elección: se aplica hasta agotar su saldo.
        assert (embargo.kind, embargo.is_recurring, embargo.total_amount) == ("garnishment", False, D(90000))

    def test_lo_de_un_empleado_que_ya_existia_se_le_cuelga(self):
        mundo = Mundo()
        mundo.importar(
            pedido(positions=(), employees=(), earnings=(EarningRow(2, "999999999", date(2025, 12, 1), Money(1000)),), deductions=()),
            dry_run=False,
        )
        assert mundo.apertura.agregados[0][0] == 44

    def test_con_una_fila_mala_no_se_escribe_nada(self):
        mundo = Mundo()
        with pytest.raises(ImportHasErrors) as e:
            mundo.importar(pedido(employees=(empleada(), empleada(3, identification="x-1"))), dry_run=False)
        assert e.value.errors == (RowError("employees", 3, "invalid_employee", "identification", "not_digits"),)
        assert mundo.nada_escrito()
        assert not mundo.uow.committed
