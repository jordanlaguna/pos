import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { ImportError } from './errors';
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

	it('lo que F10 agregó no mueve ni una cifra de las de arriba', () => {
		/*
		 * Esta factura no trae `<Impuesto>` ni `<CondicionVenta>`, así que los
		 * campos nuevos salen en su valor de reposo. Es la mitad que importa del
		 * invariante: el lector aprendió a leer más, no a leer distinto.
		 */
		expect(r.lines.every((l) => l.tax_rate === 0 && l.tax_amount === 0)).toBe(true);
		expect(r.payment_terms).toBe('cash');
		expect(r.credit_days).toBe(0);
	});

	it('ahora reconoce al emisor por su identificación', () => {
		// Es lo que permite encontrar al proveedor sin preguntarle a nadie: la
		// misma identificación es el mismo proveedor (RN-52).
		expect(r.supplier_details).toEqual({
			name: 'Distribuidora La Central S.A.',
			identification_type: '02',
			identification: '3101154998',
			email: null,
			phone: null
		});
	});

	it('la clave y el consecutivo son dos cosas distintas', () => {
		expect(r.document_number).toBe('00100001010000514161');
		expect(r.document_key).toBe('50601012600310115499800100001010000514161100514161');
		expect(r.document_key).toHaveLength(50);
	});
});

/*
 * Contra comprobantes **reales** de Hacienda, los que vienen en
 * `docs/hacienda/costa-rica/` desde abril. La factura de arriba la escribimos
 * nosotros para fijar el invariante; estas las emitió alguien de verdad, y son
 * las que dicen si el lector sirve el día que llega un correo del proveedor.
 */
describe('facturas reales del material de Hacienda', () => {
	function oficial(ruta: string): string {
		return readFileSync(
			fileURLToPath(new URL(`../../../../../docs/hacienda/costa-rica/${ruta}`, import.meta.url)),
			'utf-8'
		);
	}

	describe('una a crédito, con IVA por línea', () => {
		const r = parseHaciendaXml(
			oficial(
				'normativa/protocolos/' +
					'50606012600310134122000100001010000009369100009369.xml'
			)
		);

		it('reconoce al emisor con su cédula jurídica', () => {
			expect(r.supplier_details?.name).toBe('Plastipol de Costa Rica R V S.A.');
			expect(r.supplier_details?.identification_type).toBe('02');
			expect(r.supplier_details?.identification).toBe('3101341220');
		});

		it('la condición de venta da la cuenta por pagar y su plazo', () => {
			expect(r.payment_terms).toBe('credit');
			expect(r.credit_days).toBe(30);
		});

		it('cada línea trae la tarifa y el monto del documento', () => {
			// Los números son los del archivo: 500 kg a 2,70 → 1 350 y 175,50 de
			// IVA; 200 kg → 540 y 70,20. Es el crédito fiscal de esta compra.
			expect(r.lines).toHaveLength(2);
			expect(r.lines[0].tax_rate).toBe(13);
			expect(r.lines[0].tax_amount).toBe(175.5);
			expect(r.lines[1].tax_rate).toBe(13);
			expect(r.lines[1].tax_amount).toBe(70.2);
		});

		it('el impuesto no se deduce del subtotal sino que se lee', () => {
			// Aplicar 13 % al subtotal daría lo mismo acá, y por eso no prueba
			// nada por sí solo; lo que se comprueba es de dónde sale el número.
			const [primera] = r.lines;
			expect(primera.quantity * primera.unit_cost).toBe(1350);
			expect(primera.tax_amount).toBe(175.5);
		});
	});

	describe('otra de contado, al 1 %', () => {
		const r = parseHaciendaXml(
			oficial(
				'normativa/protocolos/' +
					'50608012600011175091400100001010000004940100004940.xml'
			)
		);

		it('la tarifa reducida se lee tal cual, no se normaliza a 13', () => {
			// Es lo que motivó RN-53: el crédito fiscal es lo que se pagó, y un
			// producto de canasta básica se compra al 1 %.
			expect(r.lines[0].tax_rate).toBe(1);
		});

		it('a crédito a un día sigue siendo a crédito', () => {
			expect(r.payment_terms).toBe('credit');
			expect(r.credit_days).toBe(1);
		});
	});

	describe('una con condición que no es ni contado ni crédito', () => {
		const r = parseHaciendaXml(
			oficial('XML-Ejemplos/' + '50616072600310170293400100002030000500153170510022.xml')
		);

		it('se trata como contado', () => {
			// `CondicionVenta` tiene más valores —apartado, consignación,
			// prepago—. Tratarlos como crédito crearía una cuenta por pagar que
			// nadie va a cobrar; como contado, no se inventa deuda.
			expect(r.payment_terms).toBe('cash');
			expect(r.credit_days).toBe(0);
		});
	});
});

/*
 * Se compara el CÓDIGO y no la frase. Comparar cadenas ataba estas pruebas al
 * idioma —cambiar una coma rompía una prueba de lectura de XML— y aun así no
 * distinguía dos errores que empezaran igual (T-803, RN-30).
 */
describe('archivos que no sirven', () => {
	function motivo(fn: () => unknown): string {
		try {
			fn();
		} catch (error) {
			if (error instanceof ImportError) return error.failure.code;
			throw error;
		}
		throw new Error('no lanzó');
	}

	it('uno que no es una factura', () => {
		expect(motivo(() => parseHaciendaXml('<Cualquiera><a>1</a></Cualquiera>'))).toBe(
			'import_not_an_invoice'
		);
	});

	it('uno que no es XML', () => {
		expect(() => parseHaciendaXml('esto no es xml')).toThrow();
	});

	it('una factura sin líneas', () => {
		const vacia = XML.replace(/<LineaDetalle>[\s\S]*<\/LineaDetalle>/, '');
		expect(motivo(() => parseHaciendaXml(vacia))).toBe('import_invoice_without_lines');
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
