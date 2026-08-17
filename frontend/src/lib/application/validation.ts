/**
 * Validación de formularios.
 *
 * Corre en el servidor, dentro de las acciones. El HTML valida en el navegador
 * como cortesía, pero nada llega al backend sin pasar por aquí: `required` en un
 * input se salta con las herramientas de desarrollo.
 */

export type Errors = Record<string, string>;

/**
 * Error que no pertenece a ningún campo (fallo del backend, credenciales malas).
 * El tipo de retorno explícito mantiene homogéneas las cargas de `fail()`: sin él
 * TypeScript infiere `{ form: string }` y la página pierde el resto de las claves.
 */
export function formError(message: string): Errors {
	return { form: message };
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

	private setIfEmpty(field: string, message: string) {
		if (!this.errors[field]) this.errors[field] = message;
	}

	/** Texto obligatorio con longitud mínima/máxima. */
	text(
		field: string,
		label: string,
		{ required = true, min = 1, max = 255 } = {}
	): string {
		const value = this.raw(field);
		if (!value) {
			if (required) this.setIfEmpty(field, `${label} es obligatorio.`);
			return '';
		}
		if (value.length < min) this.setIfEmpty(field, `${label} debe tener al menos ${min} caracteres.`);
		if (value.length > max) this.setIfEmpty(field, `${label} no puede superar ${max} caracteres.`);
		return value;
	}

	email(field: string, label = 'El correo', { required = true } = {}): string {
		const value = this.raw(field);
		if (!value) {
			if (required) this.setIfEmpty(field, `${label} es obligatorio.`);
			return '';
		}
		// Comprobación deliberadamente laxa: la verdad la tiene el servidor de correo.
		if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value))
			this.setIfEmpty(field, `${label} no tiene un formato válido.`);
		return value.toLowerCase();
	}

	/** Número decimal. Acepta coma o punto como separador. */
	decimal(
		field: string,
		label: string,
		{ required = true, min = -Infinity, max = Infinity } = {}
	): number {
		const raw = this.raw(field).replace(',', '.');
		if (!raw) {
			if (required) this.setIfEmpty(field, `${label} es obligatorio.`);
			return 0;
		}
		const value = Number(raw);
		if (!Number.isFinite(value)) {
			this.setIfEmpty(field, `${label} debe ser un número.`);
			return 0;
		}
		if (value < min) this.setIfEmpty(field, `${label} no puede ser menor que ${min}.`);
		if (value > max) this.setIfEmpty(field, `${label} no puede ser mayor que ${max}.`);
		return value;
	}

	integer(
		field: string,
		label: string,
		{ required = true, min = -Infinity, max = Infinity } = {}
	): number {
		const raw = this.raw(field);
		if (!raw) {
			if (required) this.setIfEmpty(field, `${label} es obligatorio.`);
			return 0;
		}
		if (!/^-?\d+$/.test(raw)) {
			this.setIfEmpty(field, `${label} debe ser un número entero.`);
			return 0;
		}
		const value = Number(raw);
		if (value < min) this.setIfEmpty(field, `${label} no puede ser menor que ${min}.`);
		if (value > max) this.setIfEmpty(field, `${label} no puede ser mayor que ${max}.`);
		return value;
	}

	/** Solo dígitos: teléfonos y cédulas, que no son números que se sumen. */
	digits(
		field: string,
		label: string,
		{ required = true, min = 8, max = 15 } = {}
	): string {
		const value = this.raw(field).replace(/[\s-]/g, '');
		if (!value) {
			if (required) this.setIfEmpty(field, `${label} es obligatorio.`);
			return '';
		}
		if (!/^\d+$/.test(value)) {
			this.setIfEmpty(field, `${label} solo puede contener dígitos.`);
			return value;
		}
		if (value.length < min || value.length > max)
			this.setIfEmpty(field, `${label} debe tener entre ${min} y ${max} dígitos.`);
		return value;
	}

	date(field: string, label: string, { required = true, notFuture = false } = {}): string {
		const value = this.raw(field);
		if (!value) {
			if (required) this.setIfEmpty(field, `${label} es obligatoria.`);
			return '';
		}
		const parsed = new Date(`${value}T00:00:00`);
		if (Number.isNaN(parsed.getTime())) {
			this.setIfEmpty(field, `${label} no es una fecha válida.`);
			return value;
		}
		if (notFuture && parsed.getTime() > Date.now())
			this.setIfEmpty(field, `${label} no puede estar en el futuro.`);
		return value;
	}

	password(field: string, label = 'La contraseña', { min = 6 } = {}): string {
		const value = typeof this.data[field] === 'string' ? (this.data[field] as string) : '';
		if (!value) {
			this.setIfEmpty(field, `${label} es obligatoria.`);
			return '';
		}
		if (value.length < min)
			this.setIfEmpty(field, `${label} debe tener al menos ${min} caracteres.`);
		return value;
	}

	/** Valor que debe pertenecer a un conjunto cerrado (método de pago, rol…). */
	oneOf<T extends string>(
		field: string,
		label: string,
		allowed: readonly T[],
		{ required = true } = {}
	): T | '' {
		const value = this.raw(field) as T;
		if (!value) {
			if (required) this.setIfEmpty(field, `${label} es obligatorio.`);
			return '';
		}
		if (!allowed.includes(value)) {
			this.setIfEmpty(field, `${label} no es válido.`);
			return '';
		}
		return value;
	}

	/** Añade un error que no viene de un campo concreto. */
	add(field: string, message: string) {
		this.setIfEmpty(field, message);
	}
}
