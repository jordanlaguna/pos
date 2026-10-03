import { describe, expect, it } from 'vitest';
import {
	ABSENCE_KINDS,
	CONTRACT_KINDS,
	DEDUCTION_KINDS,
	EARNING_KINDS,
	REGISTRABLE_KINDS,
	actionFields,
	employeeName,
	itemsByPayer
} from './payroll';

describe('las listas cerradas de la planilla (RN-90)', () => {
	it('los dieciséis tipos menos la baja se registran desde la pantalla', () => {
		expect(REGISTRABLE_KINDS).toHaveLength(15);
		expect(REGISTRABLE_KINDS).toEqual([
			...EARNING_KINDS,
			...ABSENCE_KINDS,
			...DEDUCTION_KINDS,
			...CONTRACT_KINDS
		]);
		expect(REGISTRABLE_KINDS).not.toContain('termination');
	});
});

describe('qué campos pide cada acción (como check_action)', () => {
	it('las extras piden horas; las vacaciones, rango y días', () => {
		expect(actionFields('overtime')).toMatchObject({ hours: true, endsOn: false, amount: false });
		expect(actionFields('vacation')).toMatchObject({ endsOn: true, days: true, hours: false });
		expect(actionFields('sick_leave_ccss')).toMatchObject({ endsOn: true, days: false });
	});

	it('las deducciones piden monto, tope y recurrencia; el embargo no es recurrente', () => {
		expect(actionFields('deduction')).toMatchObject({ amount: true, totalAmount: true, recurring: true });
		expect(actionFields('garnishment')).toMatchObject({ amount: true, totalAmount: true, recurring: false });
		expect(actionFields('bonus')).toMatchObject({ amount: true, totalAmount: false, recurring: false });
	});

	it('el aumento pide el salario nuevo y el cambio, el puesto', () => {
		expect(actionFields('raise').newSalary).toBe(true);
		expect(actionFields('position_change').position).toBe(true);
		expect(actionFields('raise').position).toBe(false);
	});
});

describe('ayudas de presentación', () => {
	it('el nombre completo salta el segundo apellido vacío', () => {
		expect(employeeName({ first_name: 'Ana', last_name_1: 'Mora', last_name_2: 'Solís' })).toBe('Ana Mora Solís');
		expect(employeeName({ first_name: 'Luis', last_name_1: 'Pérez', last_name_2: null })).toBe('Luis Pérez');
		expect(employeeName({ first_name: 'Luis', last_name_1: 'Pérez' })).toBe('Luis Pérez');
	});

	it('los rubros se reparten por quién los paga', () => {
		const grupos = itemsByPayer([
			{ payer: 'earning', concept: 'base' },
			{ payer: 'employee', concept: 'sem' },
			{ payer: 'employer', concept: 'rt' },
			{ payer: 'earning', concept: 'overtime' }
		]);
		expect(grupos.earnings.map((i) => i.concept)).toEqual(['base', 'overtime']);
		expect(grupos.deductions.map((i) => i.concept)).toEqual(['sem']);
		expect(grupos.employer.map((i) => i.concept)).toEqual(['rt']);
	});
});
