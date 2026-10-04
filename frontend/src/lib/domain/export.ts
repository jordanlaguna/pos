import { suggestedTaxCode } from './taxCodes';

/**
 * Lo que una venta necesita para salir como factura de exportación (RF-78,
 * T-727). Espejo de `app/domain/fe_export.py`, y por lo mismo que el resto del
 * dominio del comprobante: la pantalla dice que no antes de cobrar, con el
 * producto, y el servidor diría lo mismo con un código.
 *
 * Son tres cosas: la **partida arancelaria** de cada mercancía —doce dígitos
 * exactos, que los servicios (CABYS 5 a 9) no llevan—, una **tarifa que la FEE
 * admita** —no tiene balde de no sujeto, así que la 01 y la 11 no caben— y la
 * **dirección extranjera** del cliente, que ocupa el lugar de su ubicación.
 */

export const TARIFF_HEADING_LENGTH = 12;
export const FOREIGN_ADDRESS_MAX_LENGTH = 300;

/** Las tarifas que van al balde de no sujeto, que la exportación no tiene. */
const NOT_SUBJECT_CODES: readonly string[] = ['01', '11'];
/** Los CABYS que empiezan con estos dígitos son servicios. */
const SERVICE_CABYS_PREFIXES = '56789';

export function isTariffHeading(value: string): boolean {
	return new RegExp(`^\\d{${TARIFF_HEADING_LENGTH}}$`).test(value);
}

/** Mercancía salvo que el CABYS diga servicio. Sin CABYS, mercancía. */
export function isMerchandise(cabys: string | null | undefined): boolean {
	const primera = (cabys ?? '').slice(0, 1);
	return primera === '' || !SERVICE_CABYS_PREFIXES.includes(primera);
}

export interface ExportLine {
	cabys_code?: string | null;
	tariff_heading?: string | null;
	tax_code?: string | null;
	tax_rate?: number | null;
}

/** El código que va a llevar la línea: el suyo o el que se propone para su tarifa. */
export function effectiveTaxCode(line: ExportLine): string | null {
	if (line.tax_code) return line.tax_code;
	if (line.tax_rate == null) return null;
	return suggestedTaxCode(line.tax_rate);
}

export type ExportLineProblem =
	| { code: 'export_tariff_not_allowed'; taxCode: string }
	| { code: 'export_line_needs_tariff_heading' };

/** Por qué una línea no puede ir en una FEE, o `null` si puede. La tarifa primero, como el servidor. */
export function exportLineProblem(line: ExportLine): ExportLineProblem | null {
	const codigo = effectiveTaxCode(line);
	if (codigo !== null && NOT_SUBJECT_CODES.includes(codigo)) {
		return { code: 'export_tariff_not_allowed', taxCode: codigo };
	}
	if (isMerchandise(line.cabys_code) && !line.tariff_heading) {
		return { code: 'export_line_needs_tariff_heading' };
	}
	return null;
}

/** Si el cliente del extranjero tiene con qué llenar `OtrasSenasExtranjero`. */
export function hasForeignAddress(address: string | null | undefined): boolean {
	return typeof address === 'string' && address.trim() !== '';
}
