import type { ParsedLine, Product } from '$lib/types';

/**
 * Empareja las líneas de un archivo con el catálogo.
 *
 * El proveedor no usa los mismos códigos que el negocio, así que se intenta en
 * orden de confianza: primero el código de barras —que es un identificador
 * real— y solo después el nombre, que es una heurística y puede equivocarse.
 * Por eso cada línea guarda con qué criterio se emparejó: en la vista previa el
 * usuario ve si fue por código o por nombre y puede desconfiar de lo segundo.
 */

function normalizeName(value: string): string {
	return value
		.trim()
		.toLowerCase()
		.normalize('NFD')
		.replace(/[̀-ͯ]/g, '')
		// Se colapsan espacios y se quita puntuación: "Café 1820 500 g." y
		// "cafe 1820 500g" tienen que ser lo mismo.
		.replace(/[.,;:()]/g, ' ')
		.replace(/\s+/g, ' ');
}

export function matchLines(lines: ParsedLine[], products: Product[]): ParsedLine[] {
	const byBarcode = new Map<string, Product>();
	const byName = new Map<string, Product>();
	// Nombres que se repiten en el catálogo: emparejar por nombre sería una
	// moneda al aire, así que se descartan como criterio.
	const ambiguousNames = new Set<string>();

	for (const product of products) {
		const barcode = product.barcode?.trim();
		if (barcode) byBarcode.set(barcode, product);

		const name = normalizeName(product.name);
		if (byName.has(name)) ambiguousNames.add(name);
		else byName.set(name, product);
	}

	return lines.map((line) => {
		const codes = (line as ParsedLine & { allCodes?: string[] }).allCodes ?? [
			line.code
		].filter(Boolean);

		for (const code of codes) {
			const found = byBarcode.get(code.trim());
			if (found) {
				return {
					...line,
					matched: {
						id_product: found.id_product,
						name: found.name,
						barcode: found.barcode,
						stock: found.stock,
						price: Number(found.price)
					},
					matched_by: 'barcode' as const
				};
			}
		}

		const name = normalizeName(line.description);
		if (name && !ambiguousNames.has(name)) {
			const found = byName.get(name);
			if (found) {
				return {
					...line,
					matched: {
						id_product: found.id_product,
						name: found.name,
						barcode: found.barcode,
						stock: found.stock,
						price: Number(found.price)
					},
					matched_by: 'name' as const
				};
			}
		}

		return { ...line, matched: null, matched_by: null };
	});
}
