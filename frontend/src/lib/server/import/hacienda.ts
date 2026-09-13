import { XMLParser } from 'fast-xml-parser';
import { round2 } from '$lib/domain/money';
import type { ImportNote, ParsedLine, ParsedSupplier, ParseResult } from '$lib/domain/types';
import { ImportError } from './errors';

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

/**
 * Quién emitió el documento (RF-42).
 *
 * La identificación es lo que importa: con ella se reconoce al proveedor sin
 * preguntarle nada a nadie, porque la misma identificación es el mismo
 * proveedor. Sin nombre no se devuelve nada —un proveedor sin nombre no se
 * puede dar de alta— y entonces la compra se registra eligiéndolo a mano.
 */
function supplierOf(emisor: Node): ParsedSupplier | null {
	const name = text(emisor.Nombre) || text(emisor.NombreComercial);
	if (!name) return null;

	const identificacion = (emisor.Identificacion ?? {}) as Node;
	return {
		name,
		identification_type: text(identificacion.Tipo) || null,
		identification: text(identificacion.Numero) || null,
		email: text(emisor.CorreoElectronico) || null,
		// El teléfono viene partido en código de país y número; se guarda el
		// número, que es lo que alguien marca.
		phone: text((emisor.Telefono as Node)?.NumTelefono) || null
	};
}

/**
 * El impuesto de una línea, tal como lo dice el documento (RN-53).
 *
 * Una línea puede traer **varios** `<Impuesto>` —el IVA y uno selectivo, por
 * ejemplo—. La tarifa que se guarda es la del IVA (código 01), que es la que
 * va al D-104; si no hay IVA se toma la del primero, y una línea exenta no
 * trae ninguno y queda en cero.
 *
 * El monto sale de `ImpuestoNeto` cuando está, y no de la suma de los montos:
 * el neto ya descuenta `ImpuestoAsumidoEmisorFabrica`, que es impuesto que el
 * comprador **no** pagó y por lo tanto no puede acreditarse.
 */
function taxOf(line: Node): { rate: number; amount: number } {
	const impuestos = asArray(line.Impuesto);
	if (impuestos.length === 0) return { rate: 0, amount: 0 };

	const iva = impuestos.find((i) => text(i.Codigo) === '01') ?? impuestos[0];
	const neto = text(line.ImpuestoNeto);

	return {
		rate: num(iva.Tarifa),
		amount: neto ? num(neto) : impuestos.reduce((suma, i) => suma + num(i.Monto), 0)
	};
}

/**
 * `CondicionVenta` → cómo se paga.
 *
 * 01 es contado y 02 es crédito; el resto —apartado, consignación, prepago— se
 * trata como contado, que es lo que no crea una cuenta por pagar que nadie va a
 * cobrar. `PlazoCredito` solo viene en las de crédito.
 */
function paymentTermsOf(root: Node): { terms: 'cash' | 'credit'; days: number } {
	const condicion = text(root.CondicionVenta);
	if (condicion !== '02') return { terms: 'cash', days: 0 };

	const dias = Math.trunc(num(root.PlazoCredito));
	return { terms: 'credit', days: dias > 0 ? dias : 0 };
}

export function parseHaciendaXml(xml: string): ParseResult {
	const warnings: ImportNote[] = [];

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
			throw new ImportError({ code: 'import_not_an_invoice' });
		}
		root = parsed[key] as Node;
	} catch (error) {
		// El «no parece una factura» de arriba pasa tal cual; cualquier otra cosa
		// es un XML que el analizador no pudo abrir.
		throw error instanceof ImportError
			? error
			: new ImportError({ code: 'import_xml_unreadable' });
	}

	const emisor = (root.Emisor ?? {}) as Node;
	const supplierDetails = supplierOf(emisor);
	const supplier = supplierDetails?.name ?? null;
	const documentNumber = text(root.NumeroConsecutivo) || text(root.Clave) || null;
	// La clave aparte del consecutivo: son dos cosas, y la de 50 dígitos es la
	// que identifica el comprobante ante Hacienda.
	const documentKey = text(root.Clave) || null;
	const issuedAt = text(root.FechaEmision) || null;
	const { terms, days } = paymentTermsOf(root);

	const detalle = (root.DetalleServicio ?? {}) as Node;
	const rawLines = asArray(detalle.LineaDetalle);

	if (rawLines.length === 0) {
		throw new ImportError({ code: 'import_invoice_without_lines' });
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
		const tax = taxOf(raw);

		const line: ParsedLine = {
			code: codes[0] ?? '',
			description,
			quantity,
			unit_cost: unitCost,
			matched: null,
			matched_by: null,
			tax_rate: tax.rate,
			tax_amount: tax.amount
		};

		// Las facturas de servicios traen líneas sin cantidad entera; se avisa en
		// vez de descartarlas en silencio.
		if (!(quantity > 0)) {
			line.issue = { code: 'import_bad_quantity' };
		} else if (!Number.isInteger(quantity)) {
			line.issue = { code: 'import_fractional_quantity', quantity };
		}

		// Se guardan todos los códigos para el emparejado posterior.
		(line as ParsedLine & { allCodes?: string[] }).allCodes = codes;

		lines.push(line);
	}

	const conIssue = lines.filter((l) => l.issue).length;
	if (conIssue) {
		warnings.push({ code: 'import_lines_need_review', count: conIssue });
	}

	return {
		source: 'xml',
		supplier,
		document_number: documentNumber,
		issued_at: issuedAt,
		lines,
		warnings,
		supplier_details: supplierDetails,
		document_key: documentKey,
		payment_terms: terms,
		credit_days: days
	};
}
