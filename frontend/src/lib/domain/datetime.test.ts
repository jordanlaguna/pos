import { describe, expect, it } from 'vitest';
import { toLocalIso } from './datetime';

describe('toLocalIso', () => {
	it('escribe la hora local, sin Z ni desfase', () => {
		expect(toLocalIso(new Date(2026, 7, 16, 21, 43, 5))).toBe('2026-08-16T21:43:05');
	});

	it('no es UTC', () => {
		/*
		 * Es el motivo de que exista. `toISOString()` daría la misma marca en UTC,
		 * y el backend guarda en hora local del servidor —el contenedor lleva `TZ`
		 * justo por eso, que fue el defecto 8—. Mezclar las dos parte el arqueo del
		 * turno de noche en dos.
		 */
		const d = new Date(2026, 7, 16, 21, 43, 5);
		if (d.getTimezoneOffset() !== 0) {
			expect(toLocalIso(d)).not.toBe(d.toISOString().slice(0, 19));
		}
		expect(toLocalIso(d)).not.toContain('Z');
	});

	it('rellena con ceros a la izquierda', () => {
		expect(toLocalIso(new Date(2026, 0, 2, 3, 4, 5))).toBe('2026-01-02T03:04:05');
	});

	it('acepta una fecha en texto', () => {
		expect(toLocalIso('2026-08-16T21:43:05')).toBe('2026-08-16T21:43:05');
	});

	it('sin fecha usa el momento actual', () => {
		for (const vacio of [null, undefined, '', 'no es una fecha']) {
			expect(toLocalIso(vacio)).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/);
		}
	});
});
