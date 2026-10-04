import readXlsxFile from 'read-excel-file/node';

/**
 * Lector de las cuatro hojas de la importación de planilla (RF-86, RN-97):
 * puestos, empleados con su contrato, devengado por mes y deducciones.
 *
 * Una hoja por archivo, `.xlsx` o `.csv`, con la primera fila de encabezados.
 * Como en la entrada de mercadería, los encabezados se buscan por nombre —con
 * sinónimos y sin tildes— y los valores cerrados se aceptan en español
 * («cédula», «casado», «quincenal») o como los nombra el API («national»,
 * «married»): quien viene de otro sistema trae lo primero. **Acá no se valida
 * nada de fondo**: eso lo hace el backend con `dry_run`, fila por fila, con las
 * mismas reglas del formulario. Lo único que se hace es leer y traducir.
 */

export type Hoja = 'positions' | 'employees' | 'earnings' | 'deductions';
export const HOJAS: Hoja[] = ['positions', 'employees', 'earnings', 'deductions'];

type Fila = Record<string, unknown>;

/** Sinónimos por columna, por hoja. Se comparan sin tildes y en minúscula. */
const COLUMNAS: Record<Hoja, Record<string, string[]>> = {
	positions: {
		name: ['puesto', 'nombre', 'name', 'position'],
		ccss_code: ['codigo ccss', 'codigo de ocupacion', 'ocupacion ccss', 'ccss', 'ccss_code'],
		ins_code: ['codigo ins', 'ocupacion ins', 'ins', 'ins_code']
	},
	employees: {
		identification_type: ['tipo de identificacion', 'tipo identificacion', 'tipo', 'identification_type'],
		identification: ['identificacion', 'cedula', 'numero de identificacion', 'identification'],
		first_name: ['nombre', 'first_name'],
		last_name_1: ['primer apellido', 'apellido 1', 'apellido1', 'last_name_1'],
		last_name_2: ['segundo apellido', 'apellido 2', 'apellido2', 'last_name_2'],
		insured_number: ['numero de asegurado', 'asegurado', 'insured_number'],
		birth_date: ['fecha de nacimiento', 'nacimiento', 'birth_date'],
		gender: ['genero', 'sexo', 'gender'],
		marital_status: ['estado civil', 'marital_status'],
		nationality: ['nacionalidad', 'nationality'],
		phone: ['telefono', 'phone'],
		email: ['correo', 'email'],
		iban: ['iban', 'cuenta', 'cuenta iban'],
		hired_on: ['fecha de ingreso', 'ingreso', 'hired_on'],
		dependent_children: ['hijos', 'hijos a cargo', 'dependent_children'],
		spouse_credit: ['conyuge', 'credito conyuge', 'spouse_credit'],
		is_pensioner: ['pensionado', 'is_pensioner'],
		schedule: ['jornada', 'schedule'],
		position: ['puesto', 'position'],
		policy: ['poliza', 'policy'],
		period_salary: ['salario', 'salario del periodo', 'period_salary'],
		solidarista_rate: ['solidarista', 'aporte solidarista', 'solidarista_rate'],
		contract_from: ['contrato desde', 'inicio del contrato', 'contract_from'],
		vacation_days: ['vacaciones', 'dias de vacaciones', 'saldo de vacaciones', 'vacation_days']
	},
	earnings: {
		identification: ['identificacion', 'cedula', 'identification'],
		month: ['mes', 'periodo', 'month'],
		gross: ['bruto', 'salario', 'devengado', 'gross']
	},
	deductions: {
		identification: ['identificacion', 'cedula', 'identification'],
		kind: ['tipo', 'kind'],
		amount: ['cuota', 'monto', 'amount'],
		balance: ['saldo', 'balance', 'total'],
		starts_on: ['desde', 'inicio', 'starts_on'],
		ends_on: ['hasta', 'fin', 'ends_on'],
		is_recurring: ['recurrente', 'is_recurring'],
		memo: ['nota', 'detalle', 'memo']
	}
};

/** Los valores cerrados, del español al API. Lo que no está se manda tal cual. */
const VALORES: Record<string, Record<string, string>> = {
	identification_type: {
		cedula: 'national',
		'cedula nacional': 'national',
		nacional: 'national',
		dimex: 'dimex',
		nite: 'nite',
		pasaporte: 'passport',
		'permiso de trabajo': 'work_permit',
		permiso: 'work_permit'
	},
	gender: { femenino: 'F', mujer: 'F', f: 'F', masculino: 'M', hombre: 'M', m: 'M' },
	marital_status: {
		soltero: 'single',
		soltera: 'single',
		casado: 'married',
		casada: 'married',
		divorciado: 'divorced',
		divorciada: 'divorced',
		viudo: 'widowed',
		viuda: 'widowed',
		separado: 'separated',
		separada: 'separated',
		'union libre': 'free_union',
		'sin dato': 'unknown'
	},
	kind: {
		deduccion: 'deduction',
		prestamo: 'deduction',
		'pension alimentaria': 'child_support',
		pension: 'child_support',
		embargo: 'garnishment'
	}
};

const SI = new Set(['si', 's', 'x', 'true', '1', 'yes', 'verdadero']);

function normalizar(valor: unknown): string {
	return String(valor ?? '')
		.trim()
		.toLowerCase()
		.normalize('NFD')
		.replace(/[̀-ͯ]/g, '');
}

function splitCsvLine(line: string, delimiter: string): string[] {
	const out: string[] = [];
	let field = '';
	let inQuotes = false;
	for (let i = 0; i < line.length; i++) {
		const char = line[i];
		if (char === '"') {
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
	const clean = content.replace(/^﻿/, '');
	const lines = clean.split(/\r?\n/).filter((l) => l.trim());
	if (!lines.length) return [];
	const semicolons = (lines[0].match(/;/g) ?? []).length;
	const commas = (lines[0].match(/,/g) ?? []).length;
	const delimiter = semicolons > commas ? ';' : ',';
	return lines.map((l) => splitCsvLine(l, delimiter));
}

/** Una fecha como la escribe Excel, una celda de texto o un `Date`, a ISO. */
function fecha(valor: unknown): string | null {
	if (valor == null || valor === '') return null;
	if (valor instanceof Date) return valor.toISOString().slice(0, 10);
	const texto = String(valor).trim();
	const iso = /^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?$/.exec(texto);
	if (iso) return `${iso[1]}-${iso[2].padStart(2, '0')}-${(iso[3] ?? '1').padStart(2, '0')}`;
	const dmy = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(texto);
	if (dmy) return `${dmy[3]}-${dmy[2].padStart(2, '0')}-${dmy[1].padStart(2, '0')}`;
	const my = /^(\d{1,2})\/(\d{4})$/.exec(texto);
	if (my) return `${my[2]}-${my[1].padStart(2, '0')}-01`;
	return texto;
}

function numero(valor: unknown): number | null {
	if (valor == null || valor === '') return null;
	if (typeof valor === 'number') return valor;
	const limpio = String(valor).replace(/[^\d,.-]/g, '');
	// «325.000,50» o «325,000.50»: el último separador es el decimal.
	const ultimo = Math.max(limpio.lastIndexOf(','), limpio.lastIndexOf('.'));
	const entero = ultimo >= 0 ? limpio.slice(0, ultimo).replace(/[.,]/g, '') : limpio;
	const decimal = ultimo >= 0 ? limpio.slice(ultimo + 1) : '';
	const n = Number(decimal ? `${entero}.${decimal}` : entero);
	return Number.isFinite(n) ? n : null;
}

function cerrado(campo: string, valor: unknown): string {
	const crudo = String(valor ?? '').trim();
	return VALORES[campo]?.[normalizar(crudo)] ?? crudo;
}

const FECHAS = new Set(['birth_date', 'hired_on', 'contract_from', 'month', 'starts_on', 'ends_on']);
const NUMEROS = new Set(['dependent_children', 'period_salary', 'vacation_days', 'gross', 'amount', 'balance']);
const PORCENTAJES = new Set(['solidarista_rate']);
const BOOLEANOS = new Set(['spouse_credit', 'is_pensioner', 'is_recurring']);
const CERRADOS = new Set(Object.keys(VALORES));

function convertir(campo: string, valor: unknown): unknown {
	if (valor == null || valor === '') return null;
	if (FECHAS.has(campo)) return fecha(valor);
	if (NUMEROS.has(campo)) return numero(valor);
	if (PORCENTAJES.has(campo)) {
		const n = numero(valor);
		return n == null ? null : n / 100;
	}
	if (BOOLEANOS.has(campo)) return SI.has(normalizar(valor));
	if (CERRADOS.has(campo)) return cerrado(campo, valor);
	return String(valor).trim();
}

/** Las filas de una hoja, ya con los nombres del API y la fila del archivo. */
export async function leerHoja(hoja: Hoja, archivo: File): Promise<Fila[]> {
	const buffer = Buffer.from(await archivo.arrayBuffer());
	const matriz = archivo.name.toLowerCase().endsWith('.csv')
		? parseCsv(buffer.toString('utf-8'))
		: ((await readXlsxFile(buffer)) as unknown as unknown[][]);
	if (!matriz.length) return [];

	const encabezados = matriz[0].map(normalizar);
	const columnas = new Map<number, string>();
	for (const [campo, sinonimos] of Object.entries(COLUMNAS[hoja])) {
		const indice = encabezados.findIndex((h) => sinonimos.map(normalizar).includes(h));
		if (indice >= 0) columnas.set(indice, campo);
	}

	const filas: Fila[] = [];
	matriz.slice(1).forEach((celdas, i) => {
		if (!celdas.some((c) => c != null && String(c).trim() !== '')) return;
		const fila: Fila = { row: i + 2 };
		for (const [indice, campo] of columnas) fila[campo] = convertir(campo, celdas[indice]);
		filas.push(fila);
	});
	return filas;
}

/** Las plantillas, con los encabezados que esta lectura reconoce y una fila de ejemplo. */
export const PLANTILLAS: Record<Hoja, string[][]> = {
	positions: [
		['Puesto', 'Código CCSS', 'Código INS'],
		['Caja', '4211', '52']
	],
	employees: [
		[
			'Tipo de identificación', 'Identificación', 'Nombre', 'Primer apellido', 'Segundo apellido',
			'Número de asegurado', 'Fecha de nacimiento', 'Género', 'Estado civil', 'Nacionalidad', 'Teléfono',
			'Correo', 'IBAN', 'Fecha de ingreso', 'Hijos a cargo', 'Cónyuge', 'Pensionado', 'Jornada', 'Puesto',
			'Póliza', 'Salario del periodo', 'Solidarista', 'Contrato desde', 'Vacaciones'
		],
		[
			'Cédula', '101110111', 'Nombre', 'Apellido', '', '', '1990-05-20', 'F', 'Soltera', 'CR', '', '', '',
			'2024-03-01', '0', 'No', 'No', 'Quincenal', 'Caja', '', '325000', '', '', '5.5'
		]
	],
	earnings: [
		['Identificación', 'Mes', 'Bruto'],
		['101110111', '2025-12', '650000']
	],
	deductions: [
		['Identificación', 'Tipo', 'Cuota', 'Saldo', 'Desde', 'Hasta', 'Recurrente', 'Nota'],
		['101110111', 'Préstamo', '25000', '150000', '2026-02-01', '', 'Sí', 'Préstamo de la asociación']
	]
};

export function plantillaCsv(hoja: Hoja): string {
	return PLANTILLAS[hoja].map((fila) => fila.map((c) => (/[",;\n]/.test(c) ? `"${c.replace(/"/g, '""')}"` : c)).join(',')).join('\r\n');
}
