import { describe, expect, it } from 'vitest';
import {
	FOREIGN_ADDRESS_MAX_LENGTH,
	TARIFF_HEADING_LENGTH,
	effectiveTaxCode,
	exportLineProblem,
	hasForeignAddress,
	isMerchandise,
	isTariffHeading
} from './export';

/**
 * La factura de exportación en el POS (RF-78, T-727). Tiene que decir lo mismo
 * que `tests/domain/test_fe_export.py`: la caja avisa y el servidor aplica.
 */

const PARTIDA = '090111000000';
const MERCANCIA = '2316100000100';
const SERVICIO = '8595400000000';

describe('la partida arancelaria', () => {
	it('son doce dígitos exactos', () => {
		expect(TARIFF_HEADING_LENGTH).toBe(12);
		expect(isTariffHeading(PARTIDA)).toBe(true);
		for (const mala of ['0901110000', '0901110000001', '09011100000A', '']) {
			expect(isTariffHeading(mala)).toBe(false);
		}
	});
});

describe('mercancía o servicio', () => {
	it('lo dice el CABYS; sin CABYS es mercancía', () => {
		expect(isMerchandise(MERCANCIA)).toBe(true);
		expect(isMerchandise(SERVICIO)).toBe(false);
		expect(isMerchandise(null)).toBe(true);
		expect(isMerchandise('')).toBe(true);
	});
});

describe('la línea', () => {
	it('una mercancía con partida y tarifa general pasa', () => {
		expect(exportLineProblem({ cabys_code: MERCANCIA, tariff_heading: PARTIDA, tax_code: '08' })).toBeNull();
	});

	it('un servicio no necesita partida', () => {
		expect(exportLineProblem({ cabys_code: SERVICIO, tax_code: '08' })).toBeNull();
	});

	it('una mercancía sin partida, no', () => {
		for (const sin of [null, undefined, '']) {
			expect(exportLineProblem({ cabys_code: MERCANCIA, tariff_heading: sin, tax_code: '08' })).toEqual(
				{ code: 'export_line_needs_tariff_heading' }
			);
		}
	});

	it('la tarifa no sujeta no cabe, y se dice antes que la partida', () => {
		for (const codigo of ['01', '11']) {
			expect(exportLineProblem({ cabys_code: MERCANCIA, tax_code: codigo })).toEqual({
				code: 'export_tariff_not_allowed',
				taxCode: codigo
			});
		}
	});

	it('sin código vale el que se propone para la tarifa, como en el servidor', () => {
		expect(effectiveTaxCode({ tax_rate: 0.13 })).toBe('08');
		expect(exportLineProblem({ cabys_code: MERCANCIA, tariff_heading: PARTIDA, tax_rate: 0.13 })).toBeNull();
		// El 0 % no se decide acá: eso lo detiene el armador.
		expect(effectiveTaxCode({ tax_rate: 0 })).toBeNull();
		expect(effectiveTaxCode({})).toBeNull();
		expect(exportLineProblem({ cabys_code: MERCANCIA, tariff_heading: PARTIDA })).toBeNull();
	});
});

describe('la dirección extranjera', () => {
	it('tiene que haber algo', () => {
		expect(hasForeignAddress('12 Main St, Miami')).toBe(true);
		for (const sin of [null, undefined, '', '   ']) expect(hasForeignAddress(sin)).toBe(false);
		expect(FOREIGN_ADDRESS_MAX_LENGTH).toBe(300);
	});
});
