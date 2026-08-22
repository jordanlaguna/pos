import { describe, expect, it } from 'vitest';
import { Validator, formError, type FieldLabel } from './validation';

/**
 * La validación corre en el servidor, dentro de las acciones. El `required` de
 * un input se salta con las herramientas de desarrollo, así que lo que se
 * comprueba acá es lo único que separa al backend de cualquier cosa.
 *
 * Desde T-815 estas pruebas afirman **qué regla se incumplió**, no cómo se lee.
 * La frase la arma `$lib/ui/messages.ts` y se prueba ahí. Antes comparaban la
 * cadena, y por eso una de ellas llegó a afirmar «La cantidad es obligatorio»:
 * la falta de concordancia estaba en el código y la prueba la sostenía.
 */

function v(campos: Record<string, string>) {
	const form = new FormData();
	for (const [k, val] of Object.entries(campos)) form.append(k, val);
	return new Validator(form);
}

/** Rótulo de mentira. El género importa porque la concordancia sale de él. */
const L = (text: string, concord: FieldLabel['concord'] = 'm'): FieldLabel => ({ text, concord });

const NOMBRE = L('El nombre');
const CORREO = L('El correo');
const MONTO = L('El monto');
const CANTIDAD = L('La cantidad', 'f');
const TELEFONO = L('El teléfono');
const FECHA = L('La fecha', 'f');
const CLAVE = L('La contraseña', 'f');
const METODO = L('El método');

describe('formError', () => {
	it('marca un error que no es de ningún campo', () => {
		// Devuelve texto, no código: quien llama ya lo resolvió del catálogo.
		expect(formError('Credenciales incorrectas')).toEqual({ form: 'Credenciales incorrectas' });
	});
});

describe('estado del validador', () => {
	it('empieza sin errores', () => {
		expect(v({}).ok).toBe(true);
	});

	it('deja de estar ok en cuanto hay uno', () => {
		const val = v({});
		val.text('nombre', NOMBRE);
		expect(val.ok).toBe(false);
		expect(val.errors.nombre).toEqual({ code: 'validation_required', label: NOMBRE });
	});

	it('conserva el primer error de cada campo', () => {
		// El primero es el que explica la causa; los siguientes son consecuencia.
		const val = v({ x: '' });
		val.add('x', 'primero');
		val.add('x', 'segundo');
		expect(val.errors.x).toEqual({ code: 'validation_text', text: 'primero' });
	});

	it('ignora los campos que no son texto', () => {
		const form = new FormData();
		form.append('archivo', new Blob(['x']), 'x.txt');
		const val = new Validator(form);
		val.text('archivo', NOMBRE);
		expect(val.errors.archivo?.code).toBe('validation_required');
	});
});

describe('text', () => {
	it('recorta los espacios', () => {
		expect(v({ n: '  Ana  ' }).text('n', NOMBRE)).toBe('Ana');
	});

	it('exige el campo por omisión', () => {
		const val = v({ n: '   ' });
		expect(val.text('n', NOMBRE)).toBe('');
		expect(val.errors.n?.code).toBe('validation_required');
	});

	it('acepta el vacío cuando es opcional', () => {
		const val = v({ n: '' });
		expect(val.text('n', L('La nota', 'f'), { required: false })).toBe('');
		expect(val.ok).toBe(true);
	});

	it('exige la longitud mínima', () => {
		const val = v({ n: 'ab' });
		val.text('n', NOMBRE, { min: 3 });
		expect(val.errors.n).toEqual({ code: 'validation_too_short', label: NOMBRE, min: 3 });
	});

	it('y la máxima', () => {
		const val = v({ n: 'x'.repeat(10) });
		val.text('n', NOMBRE, { max: 5 });
		expect(val.errors.n).toEqual({ code: 'validation_too_long', label: NOMBRE, max: 5 });
	});
});

describe('email', () => {
	it('normaliza a minúsculas', () => {
		expect(v({ e: '  Admin@VentaSys.CR ' }).email('e', CORREO)).toBe('admin@ventasys.cr');
	});

	it('acepta lo que parece un correo', () => {
		const val = v({ e: 'a.b+c@sub.dominio.cr' });
		val.email('e', CORREO);
		expect(val.ok).toBe(true);
	});

	it('rechaza lo que no', () => {
		for (const malo of ['sin-arroba', 'a@b', 'a@b.c', 'con espacio@x.cr']) {
			const val = v({ e: malo });
			val.email('e', CORREO);
			expect(val.errors.e?.code, malo).toBe('validation_bad_email');
		}
	});

	it('exige el campo, o no si es opcional', () => {
		expect(v({ e: '' }).email('e', CORREO).length).toBe(0);
		const opcional = v({ e: '' });
		opcional.email('e', CORREO, { required: false });
		expect(opcional.ok).toBe(true);
	});
});

describe('decimal', () => {
	it('acepta coma o punto, que es como teclea la gente', () => {
		expect(v({ m: '1450,50' }).decimal('m', MONTO)).toBe(1450.5);
		expect(v({ m: '1450.50' }).decimal('m', MONTO)).toBe(1450.5);
	});

	it('rechaza lo que no es número', () => {
		const val = v({ m: 'mucho' });
		expect(val.decimal('m', MONTO)).toBe(0);
		expect(val.errors.m?.code).toBe('validation_not_a_number');
	});

	it('respeta el rango', () => {
		const bajo = v({ m: '-5' });
		bajo.decimal('m', MONTO, { min: 0 });
		expect(bajo.errors.m).toEqual({ code: 'validation_below_min', label: MONTO, min: 0 });

		const alto = v({ m: '200' });
		alto.decimal('m', MONTO, { max: 100 });
		expect(alto.errors.m).toEqual({ code: 'validation_above_max', label: MONTO, max: 100 });
	});

	it('exige el campo, o no si es opcional', () => {
		const val = v({ m: '' });
		expect(val.decimal('m', MONTO)).toBe(0);
		expect(val.errors.m?.code).toBe('validation_required');

		const opcional = v({ m: '' });
		opcional.decimal('m', MONTO, { required: false });
		expect(opcional.ok).toBe(true);
	});
});

describe('integer', () => {
	it('acepta enteros con signo', () => {
		expect(v({ c: '24' }).integer('c', CANTIDAD)).toBe(24);
		expect(v({ c: '-3' }).integer('c', CANTIDAD)).toBe(-3);
	});

	it('rechaza los decimales', () => {
		// Media unidad de arroz no existe en el mostrador.
		const val = v({ c: '1.5' });
		expect(val.integer('c', CANTIDAD)).toBe(0);
		expect(val.errors.c?.code).toBe('validation_not_an_integer');
	});

	it('respeta el rango', () => {
		const bajo = v({ c: '0' });
		bajo.integer('c', CANTIDAD, { min: 1 });
		expect(bajo.errors.c).toEqual({ code: 'validation_below_min', label: CANTIDAD, min: 1 });

		const alto = v({ c: '99' });
		alto.integer('c', CANTIDAD, { max: 10 });
		expect(alto.errors.c).toEqual({ code: 'validation_above_max', label: CANTIDAD, max: 10 });
	});

	it('el rótulo femenino conserva su género, que es lo que arregló T-815', () => {
		// Antes el mensaje se armaba acá con «es obligatorio» fijo, y salía «La
		// cantidad es obligatorio». Ahora la concordancia viaja con el rótulo.
		const val = v({ c: '' });
		val.integer('c', CANTIDAD);
		expect(val.errors.c).toEqual({ code: 'validation_required', label: CANTIDAD });
		expect(CANTIDAD.concord).toBe('f');
	});

	it('exige el campo, o no si es opcional', () => {
		const val = v({ c: '' });
		expect(val.integer('c', CANTIDAD)).toBe(0);
		expect(val.errors.c?.code).toBe('validation_required');

		const opcional = v({ c: '' });
		opcional.integer('c', CANTIDAD, { required: false });
		expect(opcional.ok).toBe(true);
	});
});

describe('digits', () => {
	it('quita espacios y guiones, que es como se escriben los teléfonos', () => {
		expect(v({ t: '8845-1230' }).digits('t', TELEFONO)).toBe('88451230');
		expect(v({ t: '2 222 3333' }).digits('t', TELEFONO)).toBe('22223333');
	});

	it('rechaza lo que no sean dígitos', () => {
		const val = v({ t: '8845abcd' });
		val.digits('t', TELEFONO);
		expect(val.errors.t?.code).toBe('validation_digits_only');
	});

	it('exige la cantidad de dígitos', () => {
		const val = v({ t: '123' });
		val.digits('t', TELEFONO);
		expect(val.errors.t).toEqual({
			code: 'validation_digit_length',
			label: TELEFONO,
			min: 8,
			max: 15
		});
	});

	it('exige el campo, o no si es opcional', () => {
		const val = v({ t: '' });
		expect(val.digits('t', TELEFONO)).toBe('');
		expect(val.errors.t?.code).toBe('validation_required');

		const opcional = v({ t: '' });
		opcional.digits('t', TELEFONO, { required: false });
		expect(opcional.ok).toBe(true);
	});
});

describe('date', () => {
	it('acepta una fecha ISO', () => {
		const val = v({ f: '1990-04-12' });
		expect(val.date('f', FECHA)).toBe('1990-04-12');
		expect(val.ok).toBe(true);
	});

	it('rechaza lo que no es fecha', () => {
		const val = v({ f: 'ayer' });
		expect(val.date('f', FECHA)).toBe('ayer');
		expect(val.errors.f?.code).toBe('validation_bad_date');
	});

	it('puede prohibir el futuro', () => {
		const manana = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
		const val = v({ f: manana });
		val.date('f', FECHA, { notFuture: true });
		expect(val.errors.f?.code).toBe('validation_future_date');
	});

	it('y aceptarlo si no se le pide', () => {
		const manana = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
		const val = v({ f: manana });
		val.date('f', FECHA);
		expect(val.ok).toBe(true);
	});

	it('exige el campo, o no si es opcional', () => {
		const val = v({ f: '' });
		expect(val.date('f', FECHA)).toBe('');
		expect(val.errors.f?.code).toBe('validation_required');

		const opcional = v({ f: '' });
		opcional.date('f', FECHA, { required: false });
		expect(opcional.ok).toBe(true);
	});
});

describe('password', () => {
	it('no recorta espacios: son parte de la contraseña', () => {
		expect(v({ p: '  clave  ' }).password('p', CLAVE)).toBe('  clave  ');
	});

	it('exige el mínimo', () => {
		const val = v({ p: 'abc' });
		val.password('p', CLAVE);
		expect(val.errors.p).toEqual({ code: 'validation_too_short', label: CLAVE, min: 6 });
	});

	it('siempre es obligatoria', () => {
		const val = v({ p: '' });
		expect(val.password('p', CLAVE)).toBe('');
		expect(val.errors.p?.code).toBe('validation_required');
	});

	it('un campo que no es texto cuenta como vacío', () => {
		const form = new FormData();
		form.append('p', new Blob(['x']), 'x.txt');
		const val = new Validator(form);
		val.password('p', CLAVE);
		expect(val.errors.p?.code).toBe('validation_required');
	});
});

describe('oneOf', () => {
	const METODOS = ['Efectivo', 'Tarjeta'] as const;

	it('acepta lo que está en la lista', () => {
		expect(v({ m: 'Efectivo' }).oneOf('m', METODO, METODOS)).toBe('Efectivo');
	});

	it('rechaza lo que no', () => {
		const val = v({ m: 'Trueque' });
		expect(val.oneOf('m', METODO, METODOS)).toBe('');
		expect(val.errors.m).toEqual({ code: 'validation_not_allowed', label: METODO });
	});

	it('exige el campo, o no si es opcional', () => {
		const val = v({ m: '' });
		expect(val.oneOf('m', METODO, METODOS)).toBe('');
		expect(val.errors.m?.code).toBe('validation_required');

		const opcional = v({ m: '' });
		opcional.oneOf('m', METODO, METODOS, { required: false });
		expect(opcional.ok).toBe(true);
	});
});
