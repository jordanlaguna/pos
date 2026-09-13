import { describe, expect, it } from 'vitest';
import { entryKindLabel, entryTitle, eventLabel, kindLabel, periodLabel } from './accounting';

/**
 * De código a frase (F11, RN-30).
 *
 * Lo que importa acá no es la traducción sino que **ningún código se quede sin
 * frase**: un `switch` al que le falta un caso devuelve una cadena vacía, y eso
 * en el libro diario es una línea sin nombre.
 */

describe('el tipo de cuenta', () => {
	it('nombra los seis', () => {
		for (const tipo of ['asset', 'liability', 'equity', 'income', 'cost', 'expense']) {
			expect(kindLabel(tipo)).not.toBe('');
			expect(kindLabel(tipo)).not.toBe(tipo);
		}
	});

	it('uno desconocido se muestra crudo y no vacío', () => {
		// Feo pero legible. Una fila vieja con un tipo que ya no existe no puede
		// dejar la columna en blanco.
		expect(kindLabel('inventado')).toBe('inventado');
	});
});

describe('cómo nació el asiento', () => {
	it('nombra los cuatro', () => {
		for (const tipo of ['auto', 'manual', 'adjustment', 'opening']) {
			expect(entryKindLabel(tipo)).not.toBe(tipo);
		}
	});

	it('uno desconocido se muestra crudo', () => {
		expect(entryKindLabel('raro')).toBe('raro');
	});
});

describe('el movimiento del mapeo', () => {
	it('nombra los siete', () => {
		for (const evento of [
			'sale',
			'return',
			'cash_close',
			'cash_movement',
			'purchase',
			'supplier_payment',
			'payroll'
		]) {
			expect(eventLabel(evento)).not.toBe(evento);
		}
	});
});

describe('el título de un asiento', () => {
	const automatico = (source_type: string, source_id: number) => ({
		kind: 'auto' as const,
		description: 'sale',
		source_type,
		source_id
	});

	it('un asiento automático se nombra por su origen', () => {
		// La descripción trae el código; lo que informa es de dónde salió.
		expect(entryTitle(automatico('sale', 412))).toContain('412');
		expect(entryTitle(automatico('stock_entry', 7))).toContain('7');
	});

	it('los seis orígenes tienen frase', () => {
		for (const origen of [
			'sale',
			'return',
			'cash_session',
			'cash_movement',
			'stock_entry',
			'supplier_payment'
		]) {
			expect(entryTitle(automatico(origen, 1))).not.toBe('sale');
		}
	});

	it('uno automático sin origen cae en su descripción', () => {
		expect(
			entryTitle({ kind: 'auto', description: 'sale', source_type: null, source_id: null })
		).toBe('sale');
	});

	it('un manual muestra lo que escribió quien lo dictó', () => {
		expect(
			entryTitle({
				kind: 'manual',
				description: 'Depreciación de octubre',
				source_type: null,
				source_id: null
			})
		).toBe('Depreciación de octubre');
	});

	it('la apertura y la reclasificación tienen su nombre aunque no traigan frase', () => {
		const apertura = entryTitle({
			kind: 'opening',
			description: 'opening',
			source_type: null,
			source_id: null
		});
		const ajuste = entryTitle({
			kind: 'adjustment',
			description: 'reclassify',
			source_type: null,
			source_id: null
		});

		expect(apertura).not.toBe('opening');
		expect(ajuste).not.toBe('reclassify');
	});
});

describe('el periodo', () => {
	it('se nombra mes sobre año', () => {
		expect(periodLabel(2026, 9)).toBe('9/2026');
	});
});
