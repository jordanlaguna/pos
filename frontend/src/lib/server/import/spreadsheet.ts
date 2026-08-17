import readXlsxFile from 'read-excel-file/node';
import { parseAmount, round2 } from '$lib/domain/money';
import type { ParsedLine, ParseResult } from '$lib/domain/types';

/**
 * Lector de planillas para entrada de mercadería: `.xlsx` y `.csv`.
 *
 * No se exige una plantilla exacta. Nadie mantiene el orden de las columnas de
 * un archivo que le mandó el proveedor, así que se buscan los encabezados por
 * nombre —con sinónimos y sin tildes— y se trabaja con lo que haya. Lo único
 * imprescindible es una columna de cantidad y algo que identifique el producto.
 */

/** Sinónimos aceptados por columna. Se comparan sin tildes y en minúscula. */
const HEADERS = {
	code: ['codigo', 'código', 'code', 'barcode', 'codigo de barras', 'cod', 'sku', 'upc', 'ean'],
	description: ['descripcion', 'descripción', 'producto', 'nombre', 'detalle', 'articulo', 'artículo', 'item'],
	quantity: ['cantidad', 'cant', 'qty', 'unidades', 'stock', 'existencias'],
	cost: ['costo', 'precio', 'costo unitario', 'precio unitario', 'p. unit', 'punit', 'valor']
} as const;

type Column = keyof typeof HEADERS;

function normalize(value: unknown): string {
	return String(value ?? '')
		.trim()
		.toLowerCase()
		.normalize('NFD')
		// Quita las tildes: "descripción" y "descripcion" tienen que dar igual.
		.replace(/[̀-ͯ]/g, '');
}

/** Divide una línea de CSV respetando comillas y comas dentro de campos. */
function splitCsvLine(line: string, delimiter: string): string[] {
	const out: string[] = [];
	let field = '';
	let inQuotes = false;

	for (let i = 0; i < line.length; i++) {
		const char = line[i];
		if (char === '"') {
			// Dos comillas seguidas dentro de un campo entrecomillado = una comilla.
			if (inQuotes && line[i + 1] === '"') {
				field += '"';
				i++;
			} else {
				inQuotes = !inQuotes;
			}
		} else if (char === delimiter && !inQuotes) {
			out.push(field);
			field = '';
		} else {
			field += char;
		}
	}
	out.push(field);
	return out.map((f) => f.trim());
}

function parseCsv(content: string): unknown[][] {
	// Se quita el BOM que Excel escribe al exportar como CSV UTF-8; si no, el
	// primer encabezado llega como "﻿codigo" y no coincide con nada.
	const clean = content.replace(/^﻿/, '');
	const lines = clean.split(/\r?\n/).filter((l) => l.trim());
	if (!lines.length) return [];

	// Excel en español exporta con punto y coma. Se decide por la primera fila.
	const semicolons = (lines[0].match(/;/g) ?? []).length;
	const commas = (lines[0].match(/,/g) ?? []).length;
	const delimiter = semicolons > commas ? ';' : ',';

	return lines.map((line) => splitCsvLine(line, delimiter));
}

/** Empareja cada columna esperada con su posición en la fila de encabezados. */
function mapColumns(header: unknown[]): Partial<Record<Column, number>> {
	const map: Partial<Record<Column, number>> = {};
	const cells = header.map(normalize);

	for (const [column, aliases] of Object.entries(HEADERS) as [Column, readonly string[]][]) {
		// Coincidencia exacta primero; si no, que el encabezado contenga el alias.
		let index = cells.findIndex((cell) => aliases.includes(cell));
		if (index === -1) {
			index = cells.findIndex((cell) => cell && aliases.some((a) => cell.includes(a)));
		}
		if (index !== -1) map[column] = index;
	}
	return map;
}

export async function parseSpreadsheet(
	buffer: Buffer,
	filename: string
): Promise<ParseResult> {
	const warnings: string[] = [];
	const isCsv = /\.csv$/i.test(filename);

	let rows: unknown[][];
	try {
		rows = isCsv
			? parseCsv(buffer.toString('utf-8'))
			: ((await readXlsxFile(buffer)) as unknown as unknown[][]);
	} catch {
		throw new Error(
			isCsv
				? 'No se pudo leer el CSV. Revisá que sea texto plano separado por comas o punto y coma.'
				: 'No se pudo leer el Excel. Guardalo como .xlsx (no .xls) e intentá de nuevo.'
		);
	}

	rows = rows.filter((row) => row.some((cell) => String(cell ?? '').trim()));
	if (rows.length < 2) {
		throw new Error('El archivo está vacío o solo tiene la fila de encabezados.');
	}

	const columns = mapColumns(rows[0]);

	if (columns.quantity === undefined) {
		throw new Error(
			'No se encontró la columna de cantidad. Debe llamarse «Cantidad» (o Cant, Unidades).'
		);
	}
	if (columns.code === undefined && columns.description === undefined) {
		throw new Error(
			'No se encontró cómo identificar el producto. Agregá una columna «Código» o «Descripción».'
		);
	}
	if (columns.cost === undefined) {
		warnings.push('No se encontró columna de costo; las líneas entran con costo cero.');
	}

	const lines: ParsedLine[] = [];

	for (let i = 1; i < rows.length; i++) {
		const row = rows[i];
		const cell = (index: number | undefined) =>
			index === undefined ? '' : String(row[index] ?? '').trim();

		const code = cell(columns.code);
		const description = cell(columns.description);
		if (!code && !description) continue; // fila en blanco intercalada

		const quantity = Number(String(cell(columns.quantity)).replace(',', '.'));
		const cost = columns.cost === undefined ? 0 : (parseAmount(cell(columns.cost)) ?? 0);

		const line: ParsedLine = {
			code,
			description: description || '(sin descripción)',
			quantity: Number.isFinite(quantity) ? quantity : 0,
			unit_cost: round2(cost),
			matched: null,
			matched_by: null
		};

		if (!(line.quantity > 0)) {
			// Se informa la fila del archivo, no el índice del arreglo: es lo que
			// el usuario ve en Excel al ir a corregirla.
			line.issue = `Cantidad inválida en la fila ${i + 1}.`;
		} else if (!Number.isInteger(line.quantity)) {
			line.issue = `Cantidad fraccionaria (${line.quantity}) en la fila ${i + 1}.`;
		}

		if (code) (line as ParsedLine & { allCodes?: string[] }).allCodes = [code];

		lines.push(line);
	}

	if (!lines.length) throw new Error('No se encontró ninguna fila con datos.');

	return {
		source: 'excel',
		supplier: null,
		document_number: null,
		issued_at: null,
		lines,
		warnings
	};
}

/** Contenido de la plantilla de ejemplo que se ofrece para descargar. */
export const TEMPLATE_CSV = [
	'Codigo;Descripcion;Cantidad;Costo',
	'7441000100015;Arroz Tio Pelon 1kg;24;1100',
	'7441000200014;Cafe 1820 500g;12;3400',
	'7441000300013;Leche Dos Pinos 1L;36;980'
].join('\r\n');
