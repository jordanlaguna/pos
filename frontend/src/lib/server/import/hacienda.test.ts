import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { parseHaciendaXml } from './hacienda';

/**
 * Caracterización del lector de facturas de proveedor (T-104b).
 *
 * Los números vienen de `.specify/progress.json` →
 * `invariantes_verificados.entrada_xml_hacienda`, que hasta ahora solo se
 * comprobaban a mano subiendo el archivo. La factura de prueba está en
 * `tests/fixtures/` y reproduce el caso completo: 4 líneas, entran 3,
 * 42 unidades y ₡79 800.
 */

const XML = readFileSync(
	fileURLToPath(new URL('../../../../tests/fixtures/factura-proveedor-v43.xml', import.meta.url)),
	'utf-8'
);

describe('el invariante de progress.json', () => {
	const r = parseHaciendaXml(XML);

	it('reconoce al proveedor y el documento', () => {
		expect(r.supplier).toBe('Distribuidora La Central S.A.');
		expect(r.document_number).toBe('00100001010000514161');
		expect(r.source).toBe('xml');
	});

	it('lee las cuatro líneas', () => {
		expect(r.lines).toHaveLength(4);
	});

	it('las tres que son inventario suman 42 unidades y ₡79 800', () => {
		// La de cantidad 0,5 no es una unidad de inventario y queda fuera.
		const utiles = r.lines.filter((l) => !l.issue);
		expect(utiles).toHaveLength(3);
		expect(utiles.reduce((acc, l) => acc + l.quantity, 0)).toBe(42);
		expect(utiles.reduce((acc, l) => acc + l.unit_cost * l.quantity, 0)).toBe(79800);
	});

	it('el café se toma a 3 400 neto y no a 3 600 de lista', () => {
		/*
		 * Es la regla que más plata mueve de este lector. Cuando la línea trae
		 * descuento, `PrecioUnitario` es el de lista y `SubTotal` ya viene neto:
		 * el costo real es SubTotal/Cantidad. Tomar el precio de lista inflaría el
		 * costo de todo el inventario recibido con descuento.
		 */
		const cafe = r.lines.find((l) => l.description.includes('Cafe'))!;
		expect(cafe.quantity).toBe(15);
		expect(cafe.unit_cost).toBe(3400);
		expect(cafe.unit_cost * cafe.quantity).toBe(51000);
	});

	it('la línea de servicio se marca en vez de colarse', () => {
		const servicio = r.lines.find((l) => l.description.includes('transporte'))!;
		expect(servicio.quantity).toBe(0.5);
		expect(servicio.issue).toBeTruthy();
	});

	it('prefiere el código comercial y cae al CABYS cuando no hay', () => {
		const arroz = r.lines.find((l) => l.description.includes('Arroz'))!;
		expect(arroz.code).toBe('7441029001057');

		const chiverre = r.lines.find((l) => l.description.includes('Chiverre'))!;
		expect(chiverre.code).toBe('0113200000100');
	});

	it('una línea sin monto queda con costo cero, no con basura', () => {
		// Mercadería de obsequio del proveedor: entra al inventario a costo cero.
		const chiverre = r.lines.find((l) => l.description.includes('Chiverre'))!;
		expect(chiverre.unit_cost).toBe(0);
		expect(chiverre.quantity).toBe(3);
	});
});

describe('archivos que no sirven', () => {
	it('uno que no es una factura', () => {
		expect(() => parseHaciendaXml('<Cualquiera><a>1</a></Cualquiera>')).toThrow(
			/no parece una factura/i
		);
	});

	it('uno que no es XML', () => {
		expect(() => parseHaciendaXml('esto no es xml')).toThrow();
	});

	it('una factura sin líneas', () => {
		const vacia = XML.replace(/<LineaDetalle>[\s\S]*<\/LineaDetalle>/, '');
		expect(() => parseHaciendaXml(vacia)).toThrow(/no tiene líneas/i);
	});
});

describe('otros comprobantes con la misma estructura', () => {
	it('un tiquete electrónico también se lee', () => {
		// A veces es lo que manda el proveedor.
		const tiquete = XML.replace(/FacturaElectronica/g, 'TiqueteElectronico');
		expect(parseHaciendaXml(tiquete).lines).toHaveLength(4);
	});

	it('y una nota de crédito', () => {
		const nota = XML.replace(/FacturaElectronica/g, 'NotaCreditoElectronica');
		expect(parseHaciendaXml(nota).lines).toHaveLength(4);
	});
});
