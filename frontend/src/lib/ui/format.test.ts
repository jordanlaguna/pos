import { describe, expect, it } from 'vitest';
import {
	formatDate,
	formatDateTime,
	formatDayLabel,
	formatRelative,
	formatTime,
	toDateInput
} from './format';

/**
 * Las fechas hablan el idioma de la pantalla (T-806).
 *
 * Lo que se comprueba es lo que de verdad cambia: **el orden** y **los nombres
 * de los meses**. El 15 de agosto es la fecha de prueba justamente porque
 * `15/08` y `08/15` no se pueden confundir —con un día menor a 12, un orden
 * equivocado pasaría inadvertido—.
 *
 * Se pasa el idioma explícito en vez de fijar el de la petición: es el mismo
 * camino que usan las tres plantillas de documento, que emiten en el idioma de
 * la compañía y no en el de la pantalla (RN-29, T-811).
 */

const QUINCE_DE_AGOSTO = new Date(2026, 7, 15, 14, 32, 5);

describe('la fecha depende del idioma', () => {
	it('el orden cambia entre español e inglés', () => {
		expect(formatDate(QUINCE_DE_AGOSTO, 'es')).toBe('15/08/2026');
		expect(formatDate(QUINCE_DE_AGOSTO, 'en')).toBe('08/15/2026');
		// El portugués comparte el orden del español, no el del inglés.
		expect(formatDate(QUINCE_DE_AGOSTO, 'pt')).toBe('15/08/2026');
	});

	it('los meses y los días cortos cambian de nombre', () => {
		expect(formatDayLabel(QUINCE_DE_AGOSTO, 'es')).toContain('ago');
		expect(formatDayLabel(QUINCE_DE_AGOSTO, 'en')).toContain('Aug');
		expect(formatDayLabel(QUINCE_DE_AGOSTO, 'en')).toContain('Sat');
		expect(formatDayLabel(QUINCE_DE_AGOSTO, 'pt')).toContain('ago');
	});

	it('lo relativo también', () => {
		const hace5 = new Date(Date.now() - 5 * 60 * 1000);
		expect(formatRelative(hace5, 'es')).toContain('hace');
		expect(formatRelative(hace5, 'en')).toContain('ago');
		expect(formatRelative(hace5, 'pt')).toContain('há');
	});

	it('un idioma que no está cae al español en vez de romperse', () => {
		// Nunca debería llegar —el backend descarta lo que no tiene catálogo— pero
		// una fecha ilegible es peor que una fecha en el idioma equivocado.
		expect(formatDate(QUINCE_DE_AGOSTO, 'fr')).toBe('15/08/2026');
	});
});

describe('la hora no depende del idioma', () => {
	it('va en 24 horas en los tres', () => {
		// Las horas de acá son de turnos de caja y se leen en columna: «2:05 PM»
		// junto a «14:05» es una columna que no se puede comparar de un vistazo.
		for (const idioma of ['es', 'en', 'pt']) {
			expect(formatTime(QUINCE_DE_AGOSTO, idioma)).toBe('14:32:05');
			expect(formatDateTime(QUINCE_DE_AGOSTO, idioma)).toContain('14:32');
			expect(formatDateTime(QUINCE_DE_AGOSTO, idioma)).not.toContain('PM');
		}
	});
});

describe('lo que no es para leer no cambia', () => {
	it('el valor de un <input type="date"> es siempre ISO', () => {
		// Es contrato del navegador, no formato de pantalla: traducirlo rompería
		// el campo.
		for (const idioma of ['es', 'en', 'pt']) {
			expect(toDateInput(QUINCE_DE_AGOSTO)).toBe('2026-08-15');
			void idioma;
		}
	});

	it('sin fecha se muestra una raya, no «Invalid Date»', () => {
		for (const vacio of [null, undefined, '', 'no soy una fecha']) {
			expect(formatDate(vacio, 'en')).toBe('—');
		}
	});
});
