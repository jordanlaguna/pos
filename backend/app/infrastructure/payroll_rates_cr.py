"""Las tasas de planilla de Costa Rica, con su fuente (T-1204, RN-67).

**Esto es lo que se siembra, no una verdad del sistema.** Cada cifra se leyó de
la fuente oficial el día que dice `VERIFIED_AT`, y lleva la norma que la fija.
Cuando cambie una, no se edita la fila: se agrega otra con su `valid_from`
—desde el panel, `PUT /support/payroll/rates`, o acá con una fila nueva— y las
corridas pagadas siguen leyendo sus rubros congelados (RN-66).

Lo que se comprobó el 2026-09-27
--------------------------------
- **Cuotas de la CCSS.** Desde el 1 de enero de 2026 el IVM sube a 4,33 % del
  trabajador y 5,58 % del patrono (el escalonamiento que acordó la Junta
  Directiva de la CCSS en 2019). Los totales publicados son 10,83 % y 26,83 %, y
  la prueba de la siembra los suma. La página de la CCSS para patronos seguía
  mostrando las cifras de 2023 ese día; se tomaron las de la reforma, que
  coinciden en BDO, La Nación y Alegra.
- **INA.** El patrono no agrícola con menos de cinco trabajadores permanentes no
  lo paga: por eso es exento por compañía (`INA_CONCEPT`), no una fila aparte.
- **Renta.** Decreto 45333-H (La Gaceta 229, 5 de diciembre de 2025), periodo
  2026: exento hasta ₡918 000 al mes; créditos de ₡1 710 por hijo y ₡2 590 por
  cónyuge.
- **Cesantía.** Art. 29 del Código de Trabajo, como lo dejó la Ley 7983 de
  2000. Leído del texto del MTSS.
- **Salario mínimo inembargable.** Art. 172: el menor salario **mensual** del
  decreto de salarios mínimos. En el 45303-MTSS, vigente desde el 1 de enero de
  2026, es el del servicio doméstico: ₡268 731,31.
- **Incapacidad de la CCSS.** Del cuarto día paga la CCSS (art. 35 del
  Reglamento del Seguro de Salud) y los tres primeros el patrono, al menos a la
  mitad, por jurisprudencia sobre el art. 79 (MTSS, DAJ-AE-201-12).
- **Riesgo del trabajo.** El INS paga el subsidio desde la fecha del riesgo
  (art. 236): el patrono no paga días.
- **Maternidad.** Mitad la CCSS y mitad el patrono (art. 95).
- **Base mínima contributiva.** SEM ₡346 789 e IVM ₡324 590 desde enero de 2026
  (CCSS). Se siembra para avisar; cómo se cobra la diferencia está pendiente
  de decidir (T-1204).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

COUNTRY = "CR"
VERIFIED_AT = date(2026, 9, 27)
DESDE_2026 = date(2026, 1, 1)

_CCSS = (
    "CCSS, cuotas obrero-patronales vigentes desde el 1 de enero de 2026 "
    "(escalonamiento del IVM acordado por la Junta Directiva en 2019)"
)
_LPT = "Ley de Protección al Trabajador (7983), recaudado por la CCSS"
_RENTA = "Decreto 45333-H, La Gaceta 229 del 5 de diciembre de 2025"
_SALARIOS = "Decreto 45303-MTSS, Alcance 156 a La Gaceta 229 del 5 de diciembre de 2025"


@dataclass(frozen=True)
class SeedRate:
    concept: str
    payer: str
    value: Decimal
    source: str
    valid_from: date = DESDE_2026


D = Decimal

RATES: tuple[SeedRate, ...] = (
    # ------------------------------------------------------------ el trabajador
    SeedRate("sem", "employee", D("0.0550"), _CCSS),
    SeedRate("ivm", "employee", D("0.0433"), _CCSS),
    SeedRate("banco_popular", "employee", D("0.0100"), _CCSS),
    # --------------------------------------------------------------- el patrono
    SeedRate("sem", "employer", D("0.0925"), _CCSS),
    SeedRate("ivm", "employer", D("0.0558"), _CCSS),
    SeedRate("banco_popular", "employer", D("0.0025"), _CCSS),
    SeedRate("asignaciones_familiares", "employer", D("0.0500"), _CCSS),
    SeedRate("imas", "employer", D("0.0050"), _CCSS),
    SeedRate("ina", "employer", D("0.0150"), _CCSS),
    SeedRate("banco_popular_lpt", "employer", D("0.0025"), _LPT),
    SeedRate("fcl", "employer", D("0.0150"), _LPT),
    SeedRate("rop", "employer", D("0.0200"), _LPT),
    SeedRate("ins_lpt", "employer", D("0.0100"), _LPT),
    # ---------------------------------------------------------------- las reglas
    SeedRate(
        "sick_leave_employer_days",
        "rule",
        D(3),
        "Reglamento del Seguro de Salud, art. 35: la CCSS paga desde el cuarto día; "
        "los tres primeros, el patrono (MTSS, DAJ-AE-201-12)",
    ),
    SeedRate(
        "sick_leave_employer_rate",
        "rule",
        D("0.5"),
        "Jurisprudencia sobre el art. 79 del Código de Trabajo: al menos medio salario (MTSS, DAJ-AE-201-12)",
    ),
    SeedRate("ins_employer_days", "rule", D(0), "Código de Trabajo, art. 236: el INS paga desde la fecha del riesgo"),
    SeedRate("ins_employer_rate", "rule", D(0), "Código de Trabajo, art. 236"),
    SeedRate("maternity_employer_rate", "rule", D("0.5"), "Código de Trabajo, art. 95: por partes iguales con la CCSS"),
    SeedRate(
        "minimum_wage_unseizable",
        "rule",
        D("268731.31"),
        f"Código de Trabajo, art. 172: el menor salario mensual del decreto (servicio doméstico). {_SALARIOS}",
    ),
    SeedRate("minimum_contribution_base_sem", "rule", D("346789.00"), f"CCSS, base mínima contributiva. {_SALARIOS}"),
    SeedRate("minimum_contribution_base_ivm", "rule", D("324590.00"), f"CCSS, base mínima contributiva. {_SALARIOS}"),
)

#: Lo que se publicó y contra lo que se compara la suma de las filas.
PUBLISHED_TOTALS = {"employee": D("0.1083"), "employer": D("0.2683"), "on": DESDE_2026}

#: (desde, hasta, tasa) mensuales. `None` es el último tramo, sin techo.
BRACKETS: tuple[tuple[Decimal, Decimal | None, Decimal], ...] = (
    (D(0), D(918000), D(0)),
    (D(918000), D(1347000), D("0.10")),
    (D(1347000), D(2364000), D("0.15")),
    (D(2364000), D(4727000), D("0.20")),
    (D(4727000), None, D("0.25")),
)
BRACKETS_SOURCE = _RENTA

CREDITS: dict[str, Decimal] = {"child": D(1710), "spouse": D(2590)}

#: Art. 29. Por debajo del año, días en total; desde el año, días por año.
SEVERANCE: tuple[tuple[Decimal, Decimal | None, Decimal], ...] = (
    (D("0.25"), D("0.5"), D(7)),
    (D("0.5"), D(1), D(14)),
    (D(1), D(2), D("19.5")),
    (D(2), D(3), D(20)),
    (D(3), D(4), D("20.5")),
    (D(4), D(5), D(21)),
    (D(5), D(6), D("21.24")),
    (D(6), D(7), D("21.5")),
    (D(7), D(10), D(22)),
    (D(10), D(11), D("21.5")),
    (D(11), D(12), D(21)),
    (D(12), D(13), D("20.5")),
    (D(13), None, D(20)),
)
SEVERANCE_SOURCE = "Código de Trabajo, art. 29, reformado por la Ley 7983 del 16 de febrero de 2000"
#: La tabla rige desde la Ley 7983; La Gaceta 35 del 18 de febrero de 2000.
SEVERANCE_VALID_FROM = date(2000, 2, 18)
