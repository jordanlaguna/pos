"""Los archivos del mes (RN-96, RF-62, RF-85, T-1211, T-1219).

Tres casos de uso delgados: piden al modelo de lectura lo que el mes pagado
sabe de cada trabajador y se lo dan al dominio, que es quien conoce el trazado
del INS, lo que pide el formulario de la CCSS y cómo se suma la renta retenida.
Si falta un dato, el dominio lo dice entero antes de escribir nada
(`ExportDataIncomplete`).
"""

from __future__ import annotations

from app.application.ports.payroll import PayrollReports
from app.domain.errors import DomainError
from app.domain.payroll_files import (
    CcssReport,
    IncomeTaxReport,
    InsFile,
    ccss_report,
    income_tax_report,
    ins_file,
    month_period,
)


class PolicyNotFound(DomainError):
    def __init__(self, policy_id: int) -> None:
        super().__init__(f"no hay póliza {policy_id}")
        self.policy_id = policy_id


class ExportCcssReport:
    """El informe del mes para la CCSS (RF-62)."""

    def __init__(self, *, reports: PayrollReports) -> None:
        self._reports = reports

    def __call__(self, year: int, month: int) -> CcssReport:
        return ccss_report(self._reports.employer(), self._reports.month(year, month), month_period(year, month))


class ExportInsFile:
    """El archivo del mes para el INS, de una póliza (RF-85).

    Van los trabajadores cuya póliza efectiva es esa: la del contrato o, si el
    contrato no dice, la de la compañía por omisión.
    """

    def __init__(self, *, reports: PayrollReports) -> None:
        self._reports = reports

    def __call__(self, year: int, month: int, policy_id: int) -> InsFile:
        numero = self._reports.policy_number(policy_id)
        if numero is None:
            raise PolicyNotFound(policy_id)
        suyos = [w for w in self._reports.month(year, month) if w.policy_id == policy_id]
        return ins_file(self._reports.employer(), numero, suyos, month_period(year, month))


class IncomeTaxSummary:
    """La renta retenida del mes, insumo de la declaración (RF-62, RN-73)."""

    def __init__(self, *, reports: PayrollReports) -> None:
        self._reports = reports

    def __call__(self, year: int, month: int) -> IncomeTaxReport:
        return income_tax_report(self._reports.month(year, month), month_period(year, month))
