import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it, vi } from 'vitest';
import type { CheckoutRejection } from '$lib/application/checkout';
import type { FieldLabel, ValidationError } from '$lib/application/validation';
import type { CartRejection } from '$lib/domain/cart';
import type { ImportFailure, ImportNote } from '$lib/domain/types';
import {
	API_CODES,
	apiMessage,
	cartMessage,
	checkoutMessage,
	firstError,
	importFailureMessage,
	importMessage,
	paymentLabel,
	POS_CODES,
	validationErrors,
	validationMessage
} from './messages';

/**
 * Que cada código tenga su frase.
 *
 * El `switch` exhaustivo ya obliga a escribir un caso por código, pero no
 * comprueba que la CLAVE exista en el catálogo: Paraglide compila una clave
 * ausente del idioma base a una cadena vacía, y eso en la pantalla del cajero es
 * un aviso en blanco. Estas pruebas recorren todos los códigos y exigen texto.
 *
 * La lista se escribe a mano a propósito: si alguien agrega un código al dominio
 * y no lo agrega acá, el `switch` de `messages.ts` ya no compila, así que las dos
 * mitades se sostienen entre ellas.
 */

const RECHAZOS_DE_CARRITO: CartRejection[] = [
	{ code: 'cart_quantity_not_positive' },
	{ code: 'cart_out_of_stock', product: 'Arroz 1 kg' },
	{ code: 'cart_reserved_elsewhere', free: 1, product: 'Arroz 1 kg', reserved: 2 },
	{ code: 'cart_only_units', stock: 3, product: 'Arroz 1 kg' },
	{ code: 'cart_only_units_with_current', stock: 3, product: 'Arroz 1 kg', current: 2 },
	{ code: 'cart_only_free_units', free: 7, product: 'Arroz 1 kg' },
	{ code: 'cart_max_tickets', max: 8 },
	{ code: 'cart_line_not_found' }
];

const RECHAZOS_DE_COBRO: CheckoutRejection[] = [
	{ code: 'checkout_no_lines' },
	{ code: 'checkout_bad_sale_number' },
	{ code: 'checkout_product_gone' },
	{ code: 'checkout_bad_quantity', product: 'Arroz 1 kg' },
	{ code: 'checkout_insufficient_stock', product: 'Escaso', available: 2 },
	{ code: 'checkout_cash_short' }
];

describe('cartMessage', () => {
	it.each(RECHAZOS_DE_CARRITO.map((r) => [r.code, r] as const))(
		'%s tiene frase y no queda vacía',
		(_code, rechazo) => {
			const frase = cartMessage(rechazo);
			expect(frase.trim().length).toBeGreaterThan(0);
			// Una clave que falta en el catálogo compila a cadena vacía; esto lo caza.
			expect(frase).not.toContain('undefined');
		}
	);

	it('mete los datos en la frase, no solo la plantilla', () => {
		const frase = cartMessage({
			code: 'cart_reserved_elsewhere',
			free: 1,
			product: 'Arroz 1 kg',
			reserved: 2
		});
		expect(frase).toContain('Arroz 1 kg');
		expect(frase).toContain('1');
		expect(frase).toContain('2');
	});
});

describe('checkoutMessage', () => {
	it.each(RECHAZOS_DE_COBRO.map((r) => [r.code, r] as const))(
		'%s tiene frase y no queda vacía',
		(_code, rechazo) => {
			const frase = checkoutMessage(rechazo);
			expect(frase.trim().length).toBeGreaterThan(0);
			expect(frase).not.toContain('undefined');
		}
	);

	it('nombra el producto y lo que queda', () => {
		const frase = checkoutMessage({
			code: 'checkout_insufficient_stock',
			product: 'Escaso',
			available: 2
		});
		expect(frase).toContain('Escaso');
		expect(frase).toContain('2');
	});
});

describe('validationMessage', () => {
	const MONTO: FieldLabel = { text: 'El monto', concord: 'm' };
	const CANTIDAD: FieldLabel = { text: 'La cantidad', concord: 'f' };
	const DECIMALES: FieldLabel = { text: 'Los decimales', concord: 'mp' };
	const NOTAS: FieldLabel = { text: 'Las notas', concord: 'fp' };

	const TODOS: ValidationError[] = [
		{ code: 'validation_required', label: MONTO },
		{ code: 'validation_not_allowed', label: MONTO },
		{ code: 'validation_too_short', label: MONTO, min: 3 },
		{ code: 'validation_too_long', label: MONTO, max: 5 },
		{ code: 'validation_not_a_number', label: MONTO },
		{ code: 'validation_not_an_integer', label: MONTO },
		{ code: 'validation_below_min', label: MONTO, min: 0 },
		{ code: 'validation_above_max', label: MONTO, max: 100 },
		{ code: 'validation_bad_email', label: MONTO },
		{ code: 'validation_digits_only', label: MONTO },
		{ code: 'validation_digit_length', label: MONTO, min: 8, max: 15 },
		{ code: 'validation_bad_date', label: MONTO },
		{ code: 'validation_future_date', label: MONTO },
		{ code: 'validation_text', text: 'Credenciales incorrectas' }
	];

	it.each(TODOS.map((e) => [e.code, e] as const))('%s tiene frase', (_code, error) => {
		const frase = validationMessage(error);
		expect(frase.trim().length).toBeGreaterThan(0);
		expect(frase).not.toContain('undefined');
	});

	/*
	 * La razón de ser de T-815. El validador viejo escribía «es obligatorio» fijo,
	 * así que todo campo femenino salía mal: «La categoría es obligatorio», «La
	 * cédula es obligatorio», «La dirección es obligatorio». Y con los plurales
	 * peor: «Los decimales es obligatorio».
	 */
	it('concuerda en género y número', () => {
		expect(validationMessage({ code: 'validation_required', label: MONTO })).toBe(
			'El monto es obligatorio.'
		);
		expect(validationMessage({ code: 'validation_required', label: CANTIDAD })).toBe(
			'La cantidad es obligatoria.'
		);
		expect(validationMessage({ code: 'validation_required', label: DECIMALES })).toBe(
			'Los decimales son obligatorios.'
		);
		expect(validationMessage({ code: 'validation_required', label: NOTAS })).toBe(
			'Las notas son obligatorias.'
		);
	});

	it('y también al decir que algo no es válido', () => {
		expect(validationMessage({ code: 'validation_not_allowed', label: CANTIDAD })).toBe(
			'La cantidad no es válida.'
		);
		expect(validationMessage({ code: 'validation_not_allowed', label: MONTO })).toBe(
			'El monto no es válido.'
		);
	});

	it('mete los números en la frase', () => {
		expect(validationMessage({ code: 'validation_digit_length', label: MONTO, min: 8, max: 15 }))
			.toBe('El monto debe tener entre 8 y 15 dígitos.');
	});

	it('el texto ya resuelto pasa tal cual', () => {
		expect(validationMessage({ code: 'validation_text', text: 'Sin conexión' })).toBe(
			'Sin conexión'
		);
	});
});

describe('validationErrors y firstError', () => {
	const NOMBRE: FieldLabel = { text: 'El nombre', concord: 'm' };
	const FECHA: FieldLabel = { text: 'La fecha', concord: 'f' };

	it('convierte todo el mapa a frases, conservando los campos', () => {
		const frases = validationErrors({
			name: { code: 'validation_required', label: NOMBRE },
			date: { code: 'validation_bad_date', label: FECHA }
		});
		expect(frases).toEqual({
			name: 'El nombre es obligatorio.',
			date: 'La fecha no es una fecha válida.'
		});
	});

	it('el primero es el que explica la causa', () => {
		expect(
			firstError({
				name: { code: 'validation_required', label: NOMBRE },
				date: { code: 'validation_bad_date', label: FECHA }
			})
		).toBe('El nombre es obligatorio.');
	});

	it('sin errores no hay frase', () => {
		expect(firstError({})).toBe('');
	});
});

describe('apiMessage', () => {
	/**
	 * Datos de muestra por código. Los que llevan datos van con datos: una frase
	 * a la que le falta un dato sale con un hueco, y un hueco en la pantalla del
	 * cajero es peor que un aviso genérico.
	 */
	const DATOS: Partial<Record<(typeof API_CODES)[number], Record<string, unknown>>> = {
		company_blocked: { state: 'suspendida' },
		cash_insufficient: { available: 1000 },
		duplicate_sale_number: { sale_number: '0001' },
		invalid_sale_line: { product_id: 7, product: 'Arroz 1 kg' },
		product_not_found: { product_id: 7 },
		product_without_price: { product_id: 7, product: 'Arroz 1 kg' },
		insufficient_stock: { product: 'Arroz 1 kg', available: 2, requested: 5 },
		totals_mismatch: { field: 'tax', declared: 100, computed: 565.5 },
		insufficient_payment: { received: 100, total: 4915.5 },
		not_sold_in_this_sale: { product_id: 7 },
		invalid_return_quantity: { product: 'Arroz 1 kg' },
		excessive_return: { product: 'Arroz 1 kg', remaining: 2 },
		duplicate_document: { document_number: 'F-88', loaded_at: '2026-08-01T10:00:00' },
		invalid_entry_line: { line: 3 },
		entry_product_not_found: { product_id: 7 },
		entry_missing_barcode: { line: 2 },
		barcode_taken: { barcode: '7441029001057' },
		entry_line_without_product: { line: 4 },
		entry_cannot_cancel: { product: 'Arroz 1 kg', available: 1, added: 3 },
		category_name_taken: { name: 'Congelados' },
		invalid_role: { role: 'jefe' }
	};

	it.each(API_CODES.map((code) => [code] as const))('%s tiene frase', (code) => {
		const frase = apiMessage({ status: 400, code, data: DATOS[code] ?? {} });
		expect(frase.trim().length).toBeGreaterThan(0);
		expect(frase).not.toContain('undefined');
		// Una clave que falte en el catálogo compila a cadena vacía, y una frase a
		// la que le falte un dato deja el nombre del hueco a la vista.
		expect(frase).not.toMatch(/\{[a-z_]+\}/);
	});

	it('mete los datos en la frase', () => {
		const frase = apiMessage({
			status: 400,
			code: 'insufficient_stock',
			data: { product: 'Arroz 1 kg', available: 2, requested: 5 }
		});
		expect(frase).toContain('Arroz 1 kg');
		expect(frase).toContain('2');
		expect(frase).toContain('5');
	});

	it('el campo del cotejo de totales se dice como palabra, no como nombre de columna', () => {
		const frase = apiMessage({
			status: 400,
			code: 'totals_mismatch',
			data: { field: 'tax', declared: 100, computed: 565.5 }
		});
		expect(frase).toContain('impuesto');
		expect(frase).not.toContain('tax');
	});

	it('sin nombre de producto usa el id, y sin id lo dice', () => {
		expect(apiMessage({ code: 'product_not_found', data: { product_id: 47 } })).toContain('#47');
		expect(apiMessage({ code: 'product_not_found', data: {} })).toContain('sin identificar');
	});

	it('un código de un backend más nuevo no rompe la pantalla', () => {
		const consola = vi.spyOn(console, 'error').mockImplementation(() => {});
		const frase = apiMessage({ status: 400, code: 'algo_que_no_existe_todavia', data: {} });
		expect(frase.trim().length).toBeGreaterThan(0);
		// Se registra el código: es lo que hace falta para saber qué agregar.
		expect(consola).toHaveBeenCalled();
		consola.mockRestore();
	});

	it('lo que no es un fallo del API también tiene frase', () => {
		// En un `catch` puede caer cualquier cosa: un TypeError de una línea nuestra.
		expect(apiMessage(new TypeError('x is not a function')).trim().length).toBeGreaterThan(0);
		expect(apiMessage(null).trim().length).toBeGreaterThan(0);
	});
});

describe('importMessage', () => {
	const AVISOS: ImportNote[] = [
		{ code: 'import_lines_need_review', count: 1 },
		{ code: 'import_lines_need_review', count: 4 },
		{ code: 'import_no_cost_column' },
		{ code: 'import_bad_quantity' },
		{ code: 'import_bad_quantity_in_row', row: 7 },
		{ code: 'import_fractional_quantity', quantity: 1.5 },
		{ code: 'import_fractional_quantity_in_row', quantity: 2.5, row: 9 }
	];

	const FALLOS: ImportFailure[] = [
		{ code: 'import_csv_unreadable' },
		{ code: 'import_xlsx_unreadable' },
		{ code: 'import_sheet_empty' },
		{ code: 'import_no_quantity_column' },
		{ code: 'import_no_identifier_column' },
		{ code: 'import_no_data_rows' },
		{ code: 'import_not_an_invoice' },
		{ code: 'import_xml_unreadable' },
		{ code: 'import_invoice_without_lines' }
	];

	it.each(AVISOS.map((n) => [n.code, n] as const))('aviso %s tiene frase', (_code, aviso) => {
		const frase = importMessage(aviso);
		expect(frase.trim().length).toBeGreaterThan(0);
		expect(frase).not.toContain('undefined');
		expect(frase).not.toMatch(/\{[a-z_]+\}/);
	});

	it.each(FALLOS.map((f) => [f.code, f] as const))('fallo %s tiene frase', (_code, fallo) => {
		const frase = importFailureMessage(fallo);
		expect(frase.trim().length).toBeGreaterThan(0);
		expect(frase).not.toContain('undefined');
	});

	it('el plural del aviso de revisión concuerda', () => {
		expect(importMessage({ code: 'import_lines_need_review', count: 1 })).toContain('1 línea');
		expect(importMessage({ code: 'import_lines_need_review', count: 4 })).toContain('4 líneas');
	});

	it('la fila y la cantidad entran en la frase', () => {
		const frase = importMessage({
			code: 'import_fractional_quantity_in_row',
			quantity: 2.5,
			row: 9
		});
		expect(frase).toContain('2.5');
		expect(frase).toContain('9');
	});
});

/**
 * El contrato con el backend, comprobado.
 *
 * `app/utils/api_errors.py` declara los códigos que levanta y esta lista declara
 * los que el POS sabe decir. Si se separan, el cajero ve «Ocurrió un error
 * inesperado» en vez de lo que pasó —o peor, en una pantalla en portugués—.
 *
 * Se lee el archivo del backend y no se importa nada: son dos runtimes. Con el
 * repositorio completo la ruta existe; si no —un despliegue solo del frontend—,
 * la prueba se salta en vez de fallar por la razón equivocada.
 */
describe('los códigos del backend y los del POS dicen lo mismo', () => {
	const AQUI = dirname(fileURLToPath(import.meta.url));
	const ARCHIVO = resolve(AQUI, '../../../../backend/app/utils/api_errors.py');

	function codigosDelBackend(): string[] | null {
		let fuente: string;
		try {
			fuente = readFileSync(ARCHIVO, 'utf-8');
		} catch {
			return null;
		}
		const bloque = fuente.slice(
			fuente.indexOf('CODES: frozenset[str] = frozenset('),
			fuente.indexOf('DONE: frozenset[str]')
		);
		return [...bloque.matchAll(/^\s*"([a-z_]+)",$/gm)].map((m) => m[1]);
	}

	it('el backend no levanta ningún código que el POS no sepa decir', () => {
		const backend = codigosDelBackend();
		if (!backend) return; // sin el repositorio completo no hay nada que comparar
		expect(backend.length).toBeGreaterThan(50);
		expect(backend.filter((c) => !API_CODES.includes(c as never))).toEqual([]);
	});

	it('el POS no espera ningún código que el backend no levante', () => {
		const backend = codigosDelBackend();
		if (!backend) return;
		const propios = new Set<string>(POS_CODES);
		expect(API_CODES.filter((c) => !propios.has(c) && !backend.includes(c))).toEqual([]);
	});
});

describe('paymentLabel', () => {
	it('traduce los cuatro métodos que existen', () => {
		for (const metodo of [
			'Efectivo',
			'Tarjeta de crédito',
			'Transferencia bancaria',
			'Pago móvil'
		]) {
			expect(paymentLabel(metodo).trim().length).toBeGreaterThan(0);
		}
	});

	it('un método desconocido se muestra tal cual y no en blanco', () => {
		// Puede venir de una fila vieja de la base. Mejor el valor crudo que un hueco.
		expect(paymentLabel('Cheque')).toBe('Cheque');
	});
});
