import { XMLParser } from 'fast-xml-parser';
import { round2 } from '$lib/money';
import type { ParsedLine, ParseResult } from '$lib/types';

/**
 * Lector de facturas electrónicas de Hacienda (Costa Rica).
 *
 * Es el XML que el proveedor envía por correo. Sirve tanto la versión 4.3 como
 * la 4.4, que difieren en cómo identifican el producto: la 4.3 trae `<Codigo>`
 * suelto y la 4.4 lo reemplazó por `<CodigoCABYS>` dejando `<CodigoComercial>`
 * para el código del vendedor. Se leen todas las variantes porque en la práctica
 * conviven, y cada emisor llena unas u otras.
 *
 * Se acepta también NotaCreditoElectronica y TiqueteElectronico: comparten la
 * estructura de `DetalleServicio` y a veces es lo que manda el proveedor.
 */

const parser = new XMLParser({
	ignoreAttributes: true,
	// Los documentos vienen con espacios de nombres versionados
	// (…/v4.3/facturaElectronica). Sin esto habría que escribir el prefijo en
	// cada búsqueda y cambiaría con cada versión del esquema.
	removeNSPrefix: true,
	parseTagValue: false,
	trimValues: true
});

type Node = Record<string, unknown>;

/** Los nodos que aparecen una sola vez llegan como objeto, no como arreglo. */
function asArray(value: unknown): Node[] {
	if (value == null) return [];
	return (Array.isArray(value) ? value : [value]) as Node[];
}

function text(value: unknown): string {
	if (value == null) return '';
	if (typeof value === 'object') {
		// fast-xml-parser mete el texto en #text cuando el nodo tiene hijos.
		const inner = (value as Record<string, unknown>)['#text'];
		return inner == null ? '' : String(inner).trim();
	}
	return String(value).trim();
}

/** Los montos del XML vienen con punto decimal y sin separador de miles. */
function num(value: unknown): number {
	const raw = text(value).replace(/,/g, '');
	const parsed = Number(raw);
	return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Códigos con los que se puede reconocer el producto, en orden de preferencia.
 * El código comercial del vendedor es el que más veces coincide con el código
 * de barras que se tiene cargado; CABYS es la clasificación tributaria y sirve
 * de último recurso.
 */
function codesOf(line: Node): string[] {
	const codes: string[] = [];

	for (const entry of asArray(line.CodigoComercial)) {
		const code = text(entry?.Codigo);
		if (code) codes.push(code);
	}

	const plain = text(line.Codigo);
	if (plain) codes.push(plain);

	const cabys = text(line.CodigoCABYS);
	if (cabys) codes.push(cabys);

	return [...new Set(codes)];
}

export function parseHaciendaXml(xml: string): ParseResult {
	const warnings: string[] = [];

	let root: Node;
	try {
		const parsed = parser.parse(xml) as Node;
		// El nodo raíz cambia según el tipo de comprobante.
		const key = Object.keys(parsed).find((k) =>
			/FacturaElectronica|TiqueteElectronico|NotaCreditoElectronica|NotaDebitoElectronica|FacturaElectronicaCompra/i.test(
				k
			)
		);
		if (!key) {
			throw new Error(
				'El archivo no parece una factura electrónica: no se encontró el nodo raíz esperado.'
			);
		}
		root = parsed[key] as Node;
	} catch (error) {
		throw new Error(
			error instanceof Error && error.message.startsWith('El archivo')
				? error.message
				: 'No se pudo leer el XML. ¿Está completo y sin modificar?'
		);
	}

	const emisor = (root.Emisor ?? {}) as Node;
	const supplier = text(emisor.Nombre) || text(emisor.NombreComercial) || null;
	const documentNumber = text(root.NumeroConsecutivo) || text(root.Clave) || null;
	const issuedAt = text(root.FechaEmision) || null;

	const detalle = (root.DetalleServicio ?? {}) as Node;
	const rawLines = asArray(detalle.LineaDetalle);

	if (rawLines.length === 0) {
		throw new Error('La factura no tiene líneas de detalle.');
	}

	const lines: ParsedLine[] = [];

	for (const raw of rawLines) {
		const description = text(raw.Detalle) || text(raw.DetalleServicio) || '(sin descripción)';
		const quantity = num(raw.Cantidad);

		/*
		 * El costo unitario se toma de SubTotal/Cantidad y no de PrecioUnitario:
		 * cuando la línea trae descuento, PrecioUnitario es el de lista y el
		 * SubTotal ya viene neto. Se paga lo segundo.
		 */
		const subtotal = num(raw.SubTotal) || num(raw.MontoTotal);
		const unitCost =
			quantity > 0 && subtotal > 0 ? round2(subtotal / quantity) : num(raw.PrecioUnitario);

		const codes = codesOf(raw);

		const line: ParsedLine = {
			code: codes[0] ?? '',
			description,
			quantity,
			unit_cost: unitCost,
			matched: null,
			matched_by: null
		};

		// Las facturas de servicios traen líneas sin cantidad entera; se avisa en
		// vez de descartarlas en silencio.
		if (!(quantity > 0)) {
			line.issue = 'La línea no trae una cantidad válida.';
		} else if (!Number.isInteger(quantity)) {
			line.issue = `Cantidad fraccionaria (${quantity}); el inventario lleva unidades enteras.`;
		}

		// Se guardan todos los códigos para el emparejado posterior.
		(line as ParsedLine & { allCodes?: string[] }).allCodes = codes;

		lines.push(line);
	}

	const conIssue = lines.filter((l) => l.issue).length;
	if (conIssue) {
		warnings.push(
			`${conIssue} ${conIssue === 1 ? 'línea necesita' : 'líneas necesitan'} revisión manual.`
		);
	}

	return {
		source: 'xml',
		supplier,
		document_number: documentNumber,
		issued_at: issuedAt,
		lines,
		warnings
	};
}
