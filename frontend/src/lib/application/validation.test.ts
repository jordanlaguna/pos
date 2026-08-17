import { describe, expect, it } from 'vitest';
import { Validator, formError } from './validation';

/**
 * La validación corre en el servidor, dentro de las acciones. El `required` de
 * un input se salta con las herramientas de desarrollo, así que lo que se
 * comprueba acá es lo único que separa al backend de cualquier cosa.
 */

function v(campos: Record<string, string>) {
	const form = new FormData();
	for (const [k, val] of Object.entries(campos)) form.append(k, val);
	return new Validator(form);
}

describe('formError', () => {
	it('marca un error que no es de ningún campo', () => {
		expect(formError('Credenciales incorrectas')).toEqual({ form: 'Credenciales incorrectas' });
	});
});

describe('estado del validador', () => {
	it('empieza sin errores', () => {
		expect(v({}).ok).toBe(true);
	});

	it('deja de estar ok en cuanto hay uno', () => {
		const val = v({});
		val.text('nombre', 'El nombre');
		expect(val.ok).toBe(false);
		expect(val.errors.nombre).toBe('El nombre es obligatorio.');
	});

	it('conserva el primer error de cada campo', () => {
		// El primero es el que explica la causa; los siguientes son consecuencia.
		const val = v({ x: '' });
		val.add('x', 'primero');
		val.add('x', 'segundo');
		expect(val.errors.x).toBe('primero');
	});

	it('ignora los campos que no son texto', () => {
		const form = new FormData();
		form.append('archivo', new Blob(['x']), 'x.txt');
		const val = new Validator(form);
		val.text('archivo', 'El archivo');
		expect(val.errors.archivo).toBe('El archivo es obligatorio.');
	});
});

describe('text', () => {
	it('recorta los espacios', () => {
		expect(v({ n: '  Ana  ' }).text('n', 'El nombre')).toBe('Ana');
	});

	it('exige el campo por omisión', () => {
		const val = v({ n: '   ' });
		expect(val.text('n', 'El nombre')).toBe('');
		expect(val.errors.n).toBe('El nombre es obligatorio.');
	});

	it('acepta el vacío cuando es opcional', () => {
		const val = v({ n: '' });
		expect(val.text('n', 'La nota', { required: false })).toBe('');
		expect(val.ok).toBe(true);
	});

	it('exige la longitud mínima', () => {
		const val = v({ n: 'ab' });
		val.text('n', 'El nombre', { min: 3 });
		expect(val.errors.n).toBe('El nombre debe tener al menos 3 caracteres.');
	});

	it('y la máxima', () => {
		const val = v({ n: 'x'.repeat(10) });
		val.text('n', 'El nombre', { max: 5 });
		expect(val.errors.n).toBe('El nombre no puede superar 5 caracteres.');
	});
});

describe('email', () => {
	it('normaliza a minúsculas', () => {
		expect(v({ e: '  Admin@VentaSys.CR ' }).email('e')).toBe('admin@ventasys.cr');
	});

	it('acepta lo que parece un correo', () => {
		const val = v({ e: 'a.b+c@sub.dominio.cr' });
		val.email('e');
		expect(val.ok).toBe(true);
	});

	it('rechaza lo que no', () => {
		for (const malo of ['sin-arroba', 'a@b', 'a@b.c', 'con espacio@x.cr']) {
			const val = v({ e: malo });
			val.email('e');
			expect(val.errors.e, malo).toBe('El correo no tiene un formato válido.');
		}
	});

	it('exige el campo, o no si es opcional', () => {
		expect(v({ e: '' }).email('e').length).toBe(0);
		const opcional = v({ e: '' });
		opcional.email('e', 'El correo', { required: false });
		expect(opcional.ok).toBe(true);
	});
});

describe('decimal', () => {
	it('acepta coma o punto, que es como teclea la gente', () => {
		expect(v({ m: '1450,50' }).decimal('m', 'El monto')).toBe(1450.5);
		expect(v({ m: '1450.50' }).decimal('m', 'El monto')).toBe(1450.5);
	});

	it('rechaza lo que no es número', () => {
		const val = v({ m: 'mucho' });
		expect(val.decimal('m', 'El monto')).toBe(0);
		expect(val.errors.m).toBe('El monto debe ser un número.');
	});

	it('respeta el rango', () => {
		const bajo = v({ m: '-5' });
		bajo.decimal('m', 'El monto', { min: 0 });
		expect(bajo.errors.m).toBe('El monto no puede ser menor que 0.');

		const alto = v({ m: '200' });
		alto.decimal('m', 'El monto', { max: 100 });
		expect(alto.errors.m).toBe('El monto no puede ser mayor que 100.');
	});

	it('exige el campo, o no si es opcional', () => {
		const val = v({ m: '' });
		expect(val.decimal('m', 'El monto')).toBe(0);
		expect(val.errors.m).toBe('El monto es obligatorio.');

		const opcional = v({ m: '' });
		opcional.decimal('m', 'El monto', { required: false });
		expect(opcional.ok).toBe(true);
	});
});

describe('integer', () => {
	it('acepta enteros con signo', () => {
		expect(v({ c: '24' }).integer('c', 'La cantidad')).toBe(24);
		expect(v({ c: '-3' }).integer('c', 'La cantidad')).toBe(-3);
	});

	it('rechaza los decimales', () => {
		// Media unidad de arroz no existe en el mostrador.
		const val = v({ c: '1.5' });
		expect(val.integer('c', 'La cantidad')).toBe(0);
		expect(val.errors.c).toBe('La cantidad debe ser un número entero.');
	});

	it('respeta el rango', () => {
		const bajo = v({ c: '0' });
		bajo.integer('c', 'La cantidad', { min: 1 });
		expect(bajo.errors.c).toBe('La cantidad no puede ser menor que 1.');

		const alto = v({ c: '99' });
		alto.integer('c', 'La cantidad', { max: 10 });
		expect(alto.errors.c).toBe('La cantidad no puede ser mayor que 10.');
	});

	it('exige el campo, o no si es opcional', () => {
		const val = v({ c: '' });
		expect(val.integer('c', 'La cantidad')).toBe(0);
		expect(val.errors.c).toBe('La cantidad es obligatorio.');

		const opcional = v({ c: '' });
		opcional.integer('c', 'La cantidad', { required: false });
		expect(opcional.ok).toBe(true);
	});
});

describe('digits', () => {
	it('quita espacios y guiones, que es como se escriben los teléfonos', () => {
		expect(v({ t: '8845-1230' }).digits('t', 'El teléfono')).toBe('88451230');
		expect(v({ t: '2 222 3333' }).digits('t', 'El teléfono')).toBe('22223333');
	});

	it('rechaza lo que no sean dígitos', () => {
		const val = v({ t: '8845abcd' });
		val.digits('t', 'El teléfono');
		expect(val.errors.t).toBe('El teléfono solo puede contener dígitos.');
	});

	it('exige la cantidad de dígitos', () => {
		const val = v({ t: '123' });
		val.digits('t', 'El teléfono');
		expect(val.errors.t).toBe('El teléfono debe tener entre 8 y 15 dígitos.');
	});

	it('exige el campo, o no si es opcional', () => {
		const val = v({ t: '' });
		expect(val.digits('t', 'El teléfono')).toBe('');
		expect(val.errors.t).toBe('El teléfono es obligatorio.');

		const opcional = v({ t: '' });
		opcional.digits('t', 'El teléfono', { required: false });
		expect(opcional.ok).toBe(true);
	});
});

describe('date', () => {
	it('acepta una fecha ISO', () => {
		const val = v({ f: '1990-04-12' });
		expect(val.date('f', 'La fecha')).toBe('1990-04-12');
		expect(val.ok).toBe(true);
	});

	it('rechaza lo que no es fecha', () => {
		const val = v({ f: 'ayer' });
		expect(val.date('f', 'La fecha')).toBe('ayer');
		expect(val.errors.f).toBe('La fecha no es una fecha válida.');
	});

	it('puede prohibir el futuro', () => {
		const manana = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
		const val = v({ f: manana });
		val.date('f', 'La fecha', { notFuture: true });
		expect(val.errors.f).toBe('La fecha no puede estar en el futuro.');
	});

	it('y aceptarlo si no se le pide', () => {
		const manana = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
		const val = v({ f: manana });
		val.date('f', 'La fecha');
		expect(val.ok).toBe(true);
	});

	it('exige el campo, o no si es opcional', () => {
		const val = v({ f: '' });
		expect(val.date('f', 'La fecha')).toBe('');
		expect(val.errors.f).toBe('La fecha es obligatoria.');

		const opcional = v({ f: '' });
		opcional.date('f', 'La fecha', { required: false });
		expect(opcional.ok).toBe(true);
	});
});

describe('password', () => {
	it('no recorta espacios: son parte de la contraseña', () => {
		expect(v({ p: '  clave  ' }).password('p')).toBe('  clave  ');
	});

	it('exige el mínimo', () => {
		const val = v({ p: 'abc' });
		val.password('p');
		expect(val.errors.p).toBe('La contraseña debe tener al menos 6 caracteres.');
	});

	it('siempre es obligatoria', () => {
		const val = v({ p: '' });
		expect(val.password('p')).toBe('');
		expect(val.errors.p).toBe('La contraseña es obligatoria.');
	});

	it('un campo que no es texto cuenta como vacío', () => {
		const form = new FormData();
		form.append('p', new Blob(['x']), 'x.txt');
		const val = new Validator(form);
		val.password('p');
		expect(val.errors.p).toBe('La contraseña es obligatoria.');
	});
});

describe('oneOf', () => {
	const METODOS = ['Efectivo', 'Tarjeta'] as const;

	it('acepta lo que está en la lista', () => {
		expect(v({ m: 'Efectivo' }).oneOf('m', 'El método', METODOS)).toBe('Efectivo');
	});

	it('rechaza lo que no', () => {
		const val = v({ m: 'Trueque' });
		expect(val.oneOf('m', 'El método', METODOS)).toBe('');
		expect(val.errors.m).toBe('El método no es válido.');
	});

	it('exige el campo, o no si es opcional', () => {
		const val = v({ m: '' });
		expect(val.oneOf('m', 'El método', METODOS)).toBe('');
		expect(val.errors.m).toBe('El método es obligatorio.');

		const opcional = v({ m: '' });
		opcional.oneOf('m', 'El método', METODOS, { required: false });
		expect(opcional.ok).toBe(true);
	});
});
