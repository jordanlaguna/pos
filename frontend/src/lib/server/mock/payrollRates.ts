/**
 * Las tasas de planilla que siembra la API (T-1204), para el modo simulado.
 *
 * **Generado**: no se edita a mano. Sale de
 * `backend/app/infrastructure/payroll_rates_cr.py` con
 * `python backend/generar_tasas_simulado.py`, y `test_siembra_planilla.py`
 * falla si este archivo y aquel dejan de decir lo mismo.
 */

export const PAYROLL_SEED = {
	"country": "CR",
	"verified_at": "2026-09-27",
	"required": [
		"asignaciones_familiares:employer",
		"banco_popular:employee",
		"banco_popular:employer",
		"banco_popular_lpt:employer",
		"fcl:employer",
		"imas:employer",
		"ina:employer",
		"ins_lpt:employer",
		"ivm:employee",
		"ivm:employer",
		"rop:employer",
		"sem:employee",
		"sem:employer"
	],
	"rates": [
		{
			"concept": "sem",
			"payer": "employee",
			"value": 0.055,
			"valid_from": "2026-01-01",
			"source": "CCSS, cuotas obrero-patronales vigentes desde el 1 de enero de 2026 (escalonamiento del IVM acordado por la Junta Directiva en 2019)"
		},
		{
			"concept": "ivm",
			"payer": "employee",
			"value": 0.0433,
			"valid_from": "2026-01-01",
			"source": "CCSS, cuotas obrero-patronales vigentes desde el 1 de enero de 2026 (escalonamiento del IVM acordado por la Junta Directiva en 2019)"
		},
		{
			"concept": "banco_popular",
			"payer": "employee",
			"value": 0.01,
			"valid_from": "2026-01-01",
			"source": "CCSS, cuotas obrero-patronales vigentes desde el 1 de enero de 2026 (escalonamiento del IVM acordado por la Junta Directiva en 2019)"
		},
		{
			"concept": "sem",
			"payer": "employer",
			"value": 0.0925,
			"valid_from": "2026-01-01",
			"source": "CCSS, cuotas obrero-patronales vigentes desde el 1 de enero de 2026 (escalonamiento del IVM acordado por la Junta Directiva en 2019)"
		},
		{
			"concept": "ivm",
			"payer": "employer",
			"value": 0.0558,
			"valid_from": "2026-01-01",
			"source": "CCSS, cuotas obrero-patronales vigentes desde el 1 de enero de 2026 (escalonamiento del IVM acordado por la Junta Directiva en 2019)"
		},
		{
			"concept": "banco_popular",
			"payer": "employer",
			"value": 0.0025,
			"valid_from": "2026-01-01",
			"source": "CCSS, cuotas obrero-patronales vigentes desde el 1 de enero de 2026 (escalonamiento del IVM acordado por la Junta Directiva en 2019)"
		},
		{
			"concept": "asignaciones_familiares",
			"payer": "employer",
			"value": 0.05,
			"valid_from": "2026-01-01",
			"source": "CCSS, cuotas obrero-patronales vigentes desde el 1 de enero de 2026 (escalonamiento del IVM acordado por la Junta Directiva en 2019)"
		},
		{
			"concept": "imas",
			"payer": "employer",
			"value": 0.005,
			"valid_from": "2026-01-01",
			"source": "CCSS, cuotas obrero-patronales vigentes desde el 1 de enero de 2026 (escalonamiento del IVM acordado por la Junta Directiva en 2019)"
		},
		{
			"concept": "ina",
			"payer": "employer",
			"value": 0.015,
			"valid_from": "2026-01-01",
			"source": "CCSS, cuotas obrero-patronales vigentes desde el 1 de enero de 2026 (escalonamiento del IVM acordado por la Junta Directiva en 2019)"
		},
		{
			"concept": "banco_popular_lpt",
			"payer": "employer",
			"value": 0.0025,
			"valid_from": "2026-01-01",
			"source": "Ley de Protección al Trabajador (7983), recaudado por la CCSS"
		},
		{
			"concept": "fcl",
			"payer": "employer",
			"value": 0.015,
			"valid_from": "2026-01-01",
			"source": "Ley de Protección al Trabajador (7983), recaudado por la CCSS"
		},
		{
			"concept": "rop",
			"payer": "employer",
			"value": 0.02,
			"valid_from": "2026-01-01",
			"source": "Ley de Protección al Trabajador (7983), recaudado por la CCSS"
		},
		{
			"concept": "ins_lpt",
			"payer": "employer",
			"value": 0.01,
			"valid_from": "2026-01-01",
			"source": "Ley de Protección al Trabajador (7983), recaudado por la CCSS"
		},
		{
			"concept": "sick_leave_employer_days",
			"payer": "rule",
			"value": 3.0,
			"valid_from": "2026-01-01",
			"source": "Reglamento del Seguro de Salud, art. 35: la CCSS paga desde el cuarto día; los tres primeros, el patrono (MTSS, DAJ-AE-201-12)"
		},
		{
			"concept": "sick_leave_employer_rate",
			"payer": "rule",
			"value": 0.5,
			"valid_from": "2026-01-01",
			"source": "Jurisprudencia sobre el art. 79 del Código de Trabajo: al menos medio salario (MTSS, DAJ-AE-201-12)"
		},
		{
			"concept": "ins_employer_days",
			"payer": "rule",
			"value": 0.0,
			"valid_from": "2026-01-01",
			"source": "Código de Trabajo, art. 236: el INS paga desde la fecha del riesgo"
		},
		{
			"concept": "ins_employer_rate",
			"payer": "rule",
			"value": 0.0,
			"valid_from": "2026-01-01",
			"source": "Código de Trabajo, art. 236"
		},
		{
			"concept": "maternity_employer_rate",
			"payer": "rule",
			"value": 0.5,
			"valid_from": "2026-01-01",
			"source": "Código de Trabajo, art. 95: por partes iguales con la CCSS"
		},
		{
			"concept": "minimum_wage_unseizable",
			"payer": "rule",
			"value": 268731.31,
			"valid_from": "2026-01-01",
			"source": "Código de Trabajo, art. 172: el menor salario mensual del decreto (servicio doméstico). Decreto 45303-MTSS, Alcance 156 a La Gaceta 229 del 5 de diciembre de 2025"
		},
		{
			"concept": "minimum_contribution_base_sem",
			"payer": "rule",
			"value": 346789.0,
			"valid_from": "2026-01-01",
			"source": "CCSS, base mínima contributiva. Decreto 45303-MTSS, Alcance 156 a La Gaceta 229 del 5 de diciembre de 2025"
		},
		{
			"concept": "minimum_contribution_base_ivm",
			"payer": "rule",
			"value": 324590.0,
			"valid_from": "2026-01-01",
			"source": "CCSS, base mínima contributiva. Decreto 45303-MTSS, Alcance 156 a La Gaceta 229 del 5 de diciembre de 2025"
		}
	],
	"brackets": [
		{
			"lower": 0.0,
			"upper": 918000.0,
			"rate": 0.0,
			"valid_from": "2026-01-01",
			"source": "Decreto 45333-H, La Gaceta 229 del 5 de diciembre de 2025"
		},
		{
			"lower": 918000.0,
			"upper": 1347000.0,
			"rate": 0.1,
			"valid_from": "2026-01-01",
			"source": "Decreto 45333-H, La Gaceta 229 del 5 de diciembre de 2025"
		},
		{
			"lower": 1347000.0,
			"upper": 2364000.0,
			"rate": 0.15,
			"valid_from": "2026-01-01",
			"source": "Decreto 45333-H, La Gaceta 229 del 5 de diciembre de 2025"
		},
		{
			"lower": 2364000.0,
			"upper": 4727000.0,
			"rate": 0.2,
			"valid_from": "2026-01-01",
			"source": "Decreto 45333-H, La Gaceta 229 del 5 de diciembre de 2025"
		},
		{
			"lower": 4727000.0,
			"upper": null,
			"rate": 0.25,
			"valid_from": "2026-01-01",
			"source": "Decreto 45333-H, La Gaceta 229 del 5 de diciembre de 2025"
		}
	],
	"credits": [
		{
			"concept": "child",
			"amount": 1710.0,
			"valid_from": "2026-01-01",
			"source": "Decreto 45333-H, La Gaceta 229 del 5 de diciembre de 2025"
		},
		{
			"concept": "spouse",
			"amount": 2590.0,
			"valid_from": "2026-01-01",
			"source": "Decreto 45333-H, La Gaceta 229 del 5 de diciembre de 2025"
		}
	],
	"severance": [
		{
			"years_from": 0.25,
			"years_to": 0.5,
			"days": 7.0,
			"source": "Código de Trabajo, art. 29, reformado por la Ley 7983 del 16 de febrero de 2000"
		},
		{
			"years_from": 0.5,
			"years_to": 1.0,
			"days": 14.0,
			"source": "Código de Trabajo, art. 29, reformado por la Ley 7983 del 16 de febrero de 2000"
		},
		{
			"years_from": 1.0,
			"years_to": 2.0,
			"days": 19.5,
			"source": "Código de Trabajo, art. 29, reformado por la Ley 7983 del 16 de febrero de 2000"
		},
		{
			"years_from": 2.0,
			"years_to": 3.0,
			"days": 20.0,
			"source": "Código de Trabajo, art. 29, reformado por la Ley 7983 del 16 de febrero de 2000"
		},
		{
			"years_from": 3.0,
			"years_to": 4.0,
			"days": 20.5,
			"source": "Código de Trabajo, art. 29, reformado por la Ley 7983 del 16 de febrero de 2000"
		},
		{
			"years_from": 4.0,
			"years_to": 5.0,
			"days": 21.0,
			"source": "Código de Trabajo, art. 29, reformado por la Ley 7983 del 16 de febrero de 2000"
		},
		{
			"years_from": 5.0,
			"years_to": 6.0,
			"days": 21.24,
			"source": "Código de Trabajo, art. 29, reformado por la Ley 7983 del 16 de febrero de 2000"
		},
		{
			"years_from": 6.0,
			"years_to": 7.0,
			"days": 21.5,
			"source": "Código de Trabajo, art. 29, reformado por la Ley 7983 del 16 de febrero de 2000"
		},
		{
			"years_from": 7.0,
			"years_to": 10.0,
			"days": 22.0,
			"source": "Código de Trabajo, art. 29, reformado por la Ley 7983 del 16 de febrero de 2000"
		},
		{
			"years_from": 10.0,
			"years_to": 11.0,
			"days": 21.5,
			"source": "Código de Trabajo, art. 29, reformado por la Ley 7983 del 16 de febrero de 2000"
		},
		{
			"years_from": 11.0,
			"years_to": 12.0,
			"days": 21.0,
			"source": "Código de Trabajo, art. 29, reformado por la Ley 7983 del 16 de febrero de 2000"
		},
		{
			"years_from": 12.0,
			"years_to": 13.0,
			"days": 20.5,
			"source": "Código de Trabajo, art. 29, reformado por la Ley 7983 del 16 de febrero de 2000"
		},
		{
			"years_from": 13.0,
			"years_to": null,
			"days": 20.0,
			"source": "Código de Trabajo, art. 29, reformado por la Ley 7983 del 16 de febrero de 2000"
		}
	],
	"severance_valid_from": "2000-02-18"
} as const;
