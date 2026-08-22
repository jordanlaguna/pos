/**
 * Validación de formularios.
 *
 * Corre en el servidor, dentro de las acciones. El HTML valida en el navegador
 * como cortesía, pero nada llega al backend sin pasar por aquí: `required` en un
 * input se salta con las herramientas de desarrollo.
 *
 * **Devuelve código y datos, no frases** (T-815). Antes armaba el mensaje a
 * partir de un rótulo en español —`${label} es obligatorio.`—, y eso ponía el
 * texto de la interfaz en la capa de aplicación, que no puede saber en qué
 * idioma está la pantalla. Ahora el rótulo llega ya resuelto del catálogo y lo
 * que sale de acá es la regla que se incumplió; la oración la arma
 * `$lib/ui/messages.ts`.
 */

/**
 * El rótulo de un campo, resuelto en el idioma de la sesión.
 *
 * Lleva la **concordancia** porque el español la necesita y el portugués igual:
 * «el monto es obligatorio», «la fecha es obligatoria», «los decimales son
 * obligatorios». Con solo el género, «Los decimales es obligatorio» — que es lo
 * que salía al principio de T-815—. Se declara una vez por campo en
 * `$lib/ui/fields.ts`, no en cada llamada.
 *
 * `m` masculino, `f` femenino, `mp`/`fp` sus plurales. El inglés no la usa y la
 * ignora; el mensaje declara un caso comodín.
 */
export interface FieldLabel {
	text: string;
	concord: 'm' | 'f' | 'mp' | 'fp';
}

export type ValidationError =
	| { code: 'validation_required'; label: FieldLabel }
	| { code: 'validation_too_short'; label: FieldLabel; min: number }
	| { code: 'validation_too_long'; label: FieldLabel; max: number }
	| { code: 'validation_not_a_number'; label: FieldLabel }
	| { code: 'validation_not_an_integer'; label: FieldLabel }
	| { code: 'validation_below_min'; label: FieldLabel; min: number }
	| { code: 'validation_above_max'; label: FieldLabel; max: number }
	| { code: 'validation_bad_email'; label: FieldLabel }
	| { code: 'validation_digits_only'; label: FieldLabel }
	| { code: 'validation_digit_length'; label: FieldLabel; min: number; max: number }
	| { code: 'validation_bad_date'; label: FieldLabel }
	| { code: 'validation_future_date'; label: FieldLabel }
	| { code: 'validation_not_allowed'; label: FieldLabel }
	/** Mensaje que quien llama ya resolvió del catálogo (errores del backend). */
	| { code: 'validation_text'; text: string };

export type Errors = Record<string, ValidationError>;

/**
 * Error que no pertenece a ningún campo (fallo del backend, credenciales malas).
 *
 * Devuelve texto y no un código a propósito: quien llama ya lo resolvió del
 * catálogo. Y **tiene que ser `Record<string, string>`**, igual que lo que sale
 * de `validationErrors()`: si devolviera `Errors`, el tipo de `form.errors` de
 * cada pantalla pasaría a ser la unión de las dos formas y los ocho componentes
 * que muestran errores dejarían de compilar. Es lo que hace que T-815 no toque
 * la interfaz.
 */
export function formError(text: string): Record<string, string> {
	return { form: text };
}

export class Validator {
	readonly errors: Errors = {};
	private readonly data: Record<string, FormDataEntryValue | null>;

	constructor(form: FormData) {
		this.data = Object.fromEntries(form.entries());
	}

	private raw(field: string): string {
		const value = this.data[field];
		return typeof value === 'string' ? value.trim() : '';
	}

	get ok(): boolean {
		return Object.keys(this.errors).length === 0;
	}

	private setIfEmpty(field: string, error: ValidationError) {
		if (!this.errors[field]) this.errors[field] = error;
	}

	/** Texto obligatorio con longitud mínima/máxima. */
	text(field: string, label: FieldLabel, { required = true, min = 1, max = 255 } = {}): string {
		const value = this.raw(field);
		if (!value) {
			if (required) this.setIfEmpty(field, { code: 'validation_required', label });
			return '';
		}
		if (value.length < min)
			this.setIfEmpty(field, { code: 'validation_too_short', label, min });
		if (value.length > max) this.setIfEmpty(field, { code: 'validation_too_long', label, max });
		return value;
	}

	email(field: string, label: FieldLabel, { required = true } = {}): string {
		const value = this.raw(field);
		if (!value) {
			if (required) this.setIfEmpty(field, { code: 'validation_required', label });
			return '';
		}
		// Comprobación deliberadamente laxa: la verdad la tiene el servidor de correo.
		if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value))
			this.setIfEmpty(field, { code: 'validation_bad_email', label });
		return value.toLowerCase();
	}

	/** Número decimal. Acepta coma o punto como separador. */
	decimal(
		field: string,
		label: FieldLabel,
		{ required = true, min = -Infinity, max = Infinity } = {}
	): number {
		const raw = this.raw(field).replace(',', '.');
		if (!raw) {
			if (required) this.setIfEmpty(field, { code: 'validation_required', label });
			return 0;
		}
		const value = Number(raw);
		if (!Number.isFinite(value)) {
			this.setIfEmpty(field, { code: 'validation_not_a_number', label });
			return 0;
		}
		if (value < min) this.setIfEmpty(field, { code: 'validation_below_min', label, min });
		if (value > max) this.setIfEmpty(field, { code: 'validation_above_max', label, max });
		return value;
	}

	integer(
		field: string,
		label: FieldLabel,
		{ required = true, min = -Infinity, max = Infinity } = {}
	): number {
		const raw = this.raw(field);
		if (!raw) {
			if (required) this.setIfEmpty(field, { code: 'validation_required', label });
			return 0;
		}
		if (!/^-?\d+$/.test(raw)) {
			this.setIfEmpty(field, { code: 'validation_not_an_integer', label });
			return 0;
		}
		const value = Number(raw);
		if (value < min) this.setIfEmpty(field, { code: 'validation_below_min', label, min });
		if (value > max) this.setIfEmpty(field, { code: 'validation_above_max', label, max });
		return value;
	}

	/** Solo dígitos: teléfonos y cédulas, que no son números que se sumen. */
	digits(field: string, label: FieldLabel, { required = true, min = 8, max = 15 } = {}): string {
		const value = this.raw(field).replace(/[\s-]/g, '');
		if (!value) {
			if (required) this.setIfEmpty(field, { code: 'validation_required', label });
			return '';
		}
		if (!/^\d+$/.test(value)) {
			this.setIfEmpty(field, { code: 'validation_digits_only', label });
			return value;
		}
		if (value.length < min || value.length > max)
			this.setIfEmpty(field, { code: 'validation_digit_length', label, min, max });
		return value;
	}

	date(field: string, label: FieldLabel, { required = true, notFuture = false } = {}): string {
		const value = this.raw(field);
		if (!value) {
			if (required) this.setIfEmpty(field, { code: 'validation_required', label });
			return '';
		}
		const parsed = new Date(`${value}T00:00:00`);
		if (Number.isNaN(parsed.getTime())) {
			this.setIfEmpty(field, { code: 'validation_bad_date', label });
			return value;
		}
		if (notFuture && parsed.getTime() > Date.now())
			this.setIfEmpty(field, { code: 'validation_future_date', label });
		return value;
	}

	password(field: string, label: FieldLabel, { min = 6 } = {}): string {
		const value = typeof this.data[field] === 'string' ? (this.data[field] as string) : '';
		if (!value) {
			this.setIfEmpty(field, { code: 'validation_required', label });
			return '';
		}
		if (value.length < min) this.setIfEmpty(field, { code: 'validation_too_short', label, min });
		return value;
	}

	/** Valor que debe pertenecer a un conjunto cerrado (método de pago, rol…). */
	oneOf<T extends string>(
		field: string,
		label: FieldLabel,
		allowed: readonly T[],
		{ required = true } = {}
	): T | '' {
		const value = this.raw(field) as T;
		if (!value) {
			if (required) this.setIfEmpty(field, { code: 'validation_required', label });
			return '';
		}
		if (!allowed.includes(value)) {
			this.setIfEmpty(field, { code: 'validation_not_allowed', label });
			return '';
		}
		return value;
	}

	/**
	 * Añade un error que no viene de una regla: el texto lo resuelve quien llama,
	 * que sí puede leer el catálogo.
	 */
	add(field: string, text: string) {
		this.setIfEmpty(field, { code: 'validation_text', text });
	}
}
