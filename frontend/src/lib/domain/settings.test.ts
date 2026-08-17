import { describe, expect, it } from 'vitest';
import {
	DEFAULT_SETTINGS,
	CURRENCIES,
	TEMPLATES,
	ID_TYPES,
	businessName,
	isHexColor,
	mergeSettings
} from './settings';

/**
 * `mergeSettings` es la frontera entre el JSON que devuelve el backend y el
 * resto del POS. Su contrato es no lanzar nunca: cualquier campo raro se
 * reemplaza por el de fábrica. Un POS que no abre porque la configuración
 * quedó a medias es peor que uno con la moneda por omisión.
 */

describe('mergeSettings con entradas rotas', () => {
	it('sin nada devuelve los valores de fábrica', () => {
		expect(mergeSettings(undefined)).toEqual(DEFAULT_SETTINGS);
		expect(mergeSettings(null)).toEqual(DEFAULT_SETTINGS);
		expect(mergeSettings('no soy un objeto')).toEqual(DEFAULT_SETTINGS);
		expect(mergeSettings(42)).toEqual(DEFAULT_SETTINGS);
		expect(mergeSettings([])).toEqual(DEFAULT_SETTINGS);
		expect(mergeSettings({})).toEqual(DEFAULT_SETTINGS);
	});

	it('una sección que no es objeto no arrastra a las demás', () => {
		const s = mergeSettings({ currency: 'USD', business: { nombre: 'Pulpería La Esquina' } });
		expect(s.currency).toEqual(DEFAULT_SETTINGS.currency);
		expect(s.business.name).toBe('Pulpería La Esquina');
	});

	it('conserva lo bueno y descarta lo malo dentro de la misma sección', () => {
		const s = mergeSettings({
			currency: { code: 'usd', symbol: '$', decimals: 99, thousandsSeparator: 'xx' }
		});
		expect(s.currency.code).toBe('USD'); // se normaliza a mayúsculas
		expect(s.currency.symbol).toBe('$');
		expect(s.currency.decimals).toBe(2); // 99 está fuera de 0..4
		expect(s.currency.thousandsSeparator).toBe('.'); // un separador es un carácter
	});
});

describe('mergeSettings: reglas de cada tipo de campo', () => {
	it('los textos obligatorios no aceptan el vacío', () => {
		expect(mergeSettings({ business: { nombre: '   ' } }).business.name).toBe('VentaSys');
		expect(mergeSettings({ business: { nombre: 123 } }).business.name).toBe('VentaSys');
	});

	it('los opcionales sí, porque borrarlos es una decisión', () => {
		const s = mergeSettings({ business: { phone: '   ', email: 42 } });
		expect(s.business.phone).toBe('');
		expect(s.business.email).toBe(''); // no es texto: cae al de fábrica, que es vacío
	});

	it('recorta los textos largos en vez de rechazarlos', () => {
		const s = mergeSettings({ business: { nombre: 'x'.repeat(500) } });
		expect(s.business.name).toHaveLength(120);
	});

	it('los booleanos solo aceptan booleanos', () => {
		expect(mergeSettings({ document: { showLogo: 'sí' } }).document.showLogo).toBe(true);
		expect(mergeSettings({ document: { showLogo: false } }).document.showLogo).toBe(false);
	});

	it('los números aceptan la cadena que los representa', () => {
		expect(mergeSettings({ tax: { rate: '0.04' } }).tax.rate).toBe(0.04);
	});

	it('y rechazan lo que se sale del rango o no es número', () => {
		expect(mergeSettings({ tax: { rate: 13 } }).tax.rate).toBe(0.13); // 13 no es 13 %
		expect(mergeSettings({ tax: { rate: -1 } }).tax.rate).toBe(0.13);
		expect(mergeSettings({ tax: { rate: 'mucho' } }).tax.rate).toBe(0.13);
	});

	it('lo que JavaScript convierte a cero no es una tasa del 0 % (defecto 13)', () => {
		/*
		 * `Number(null)`, `Number('')`, `Number([])` y `Number(false)` valen 0, y
		 * el 0 cae dentro del rango 0..1. La versión anterior de `num` los
		 * aceptaba, así que una fila de configuración a medias hacía que el POS
		 * cobrara 0 % de impuesto sin avisar. Cada uno de estos tiene que caer al
		 * 13 % de fábrica.
		 */
		for (const vacio of [null, undefined, '', '   ', [], false, {}]) {
			expect(mergeSettings({ tax: { rate: vacio } }).tax.rate).toBe(0.13);
		}
		// Un 0 escrito de verdad sí es 0 %: hay productos exentos.
		expect(mergeSettings({ tax: { rate: 0 } }).tax.rate).toBe(0);
		expect(mergeSettings({ tax: { rate: '0' } }).tax.rate).toBe(0);
	});

	it('el mismo cero fantasma no puede colarse en los decimales de la moneda', () => {
		expect(mergeSettings({ currency: { decimals: null } }).currency.decimals).toBe(2);
		expect(mergeSettings({ currency: { decimals: '' } }).currency.decimals).toBe(2);
		expect(mergeSettings({ currency: { decimals: 0 } }).currency.decimals).toBe(0);
	});

	it('la moneda de fábrica no arrastra el nombre del preajuste', () => {
		// `nombre` es la etiqueta del selector, no parte de la moneda. Iba dentro
		// de lo que se guardaba en el backend, escondido por un `as`.
		expect(DEFAULT_SETTINGS.currency).not.toHaveProperty('nombre');
		expect(mergeSettings({})).toEqual(DEFAULT_SETTINGS);
	});

	it('acepta el separador vacío: hay monedas que no agrupan', () => {
		expect(mergeSettings({ currency: { thousandsSeparator: '' } }).currency.thousandsSeparator).toBe('');
	});

	it('las listas cerradas solo aceptan sus valores', () => {
		expect(mergeSettings({ document: { template: 'moderna' } }).document.template).toBe('moderna');
		expect(mergeSettings({ document: { template: 'inventada' } }).document.template).toBe('tiquete');
		expect(mergeSettings({ eInvoicing: { environment: 'produccion' } }).eInvoicing.environment).toBe('produccion');
		expect(mergeSettings({ eInvoicing: { environment: 7 } }).eInvoicing.environment).toBe('sandbox');
		expect(mergeSettings({ business: { taxIdType: '02' } }).business.taxIdType).toBe('02');
		expect(mergeSettings({ business: { taxIdType: '99' } }).business.taxIdType).toBe('01');
	});

	it('el ancho del tiquete solo puede ser 58 u 80', () => {
		expect(mergeSettings({ document: { receiptWidth: 58 } }).document.receiptWidth).toBe(58);
		expect(mergeSettings({ document: { receiptWidth: 80 } }).document.receiptWidth).toBe(80);
		expect(mergeSettings({ document: { receiptWidth: 72 } }).document.receiptWidth).toBe(80);
		expect(mergeSettings({ document: { receiptWidth: 300 } }).document.receiptWidth).toBe(80);
	});
});

describe('colores', () => {
	it('acepta #rrggbb y lo normaliza a minúsculas', () => {
		expect(mergeSettings({ appearance: { accentColor: '#B45309' } }).appearance.accentColor).toBe(
			'#b45309'
		);
	});

	it('rechaza todo lo que no sea un hex de seis dígitos', () => {
		// Esto termina dentro de una etiqueta <style>: si pasa cualquier cadena,
		// pasa cualquier cosa.
		for (const malo of ['#fff', 'red', 'rgb(0,0,0)', '#12345', '#1234567', 'javascript:x', 42, null]) {
			expect(mergeSettings({ appearance: { accentColor: malo } }).appearance.accentColor).toBe(
				'#0e7490'
			);
		}
	});

	it('isHexColor decide lo mismo por su cuenta', () => {
		expect(isHexColor('#0e7490')).toBe(true);
		expect(isHexColor('#0E7490')).toBe(true);
		expect(isHexColor('#fff')).toBe(false);
		expect(isHexColor(undefined)).toBe(false);
	});
});

describe('businessName', () => {
	it('prefiere el nombre comercial', () => {
		const s = mergeSettings({ business: { nombre: 'La Esquina', legalName: 'Inversiones S.A.' } });
		expect(businessName(s)).toBe('La Esquina');
	});

	it('cae a la razón social si no hay comercial', () => {
		const s = mergeSettings({});
		s.business.name = '';
		s.business.legalName = 'Inversiones S.A.';
		expect(businessName(s)).toBe('Inversiones S.A.');
	});

	it('y a VentaSys si no hay ninguno', () => {
		const s = mergeSettings({});
		s.business.name = '';
		s.business.legalName = '';
		expect(businessName(s)).toBe('VentaSys');
	});
});

describe('catálogos', () => {
	it('la moneda de fábrica es el colón', () => {
		expect(DEFAULT_SETTINGS.currency.code).toBe('CRC');
		expect(CURRENCIES[0].code).toBe('CRC');
	});

	it('no hay códigos de moneda repetidos', () => {
		const codigos = CURRENCIES.map((m) => m.code);
		expect(new Set(codigos).size).toBe(codigos.length);
	});

	it('toda moneda trae los campos que formatMoney necesita', () => {
		for (const m of CURRENCIES) {
			expect(m.symbol.length).toBeGreaterThan(0);
			expect(m.decimals).toBeGreaterThanOrEqual(0);
			expect(m.decimalSeparator.length).toBeLessThanOrEqual(1);
			expect(m.thousandsSeparator.length).toBeLessThanOrEqual(1);
		}
	});

	it('las tres plantillas tienen identificador único y el mergeSettings las acepta', () => {
		expect(TEMPLATES).toHaveLength(3);
		for (const p of TEMPLATES) {
			expect(mergeSettings({ document: { template: p.id } }).document.template).toBe(p.id);
		}
	});

	it('todo tipo de identificación de Hacienda es aceptado', () => {
		for (const t of ID_TYPES) {
			expect(mergeSettings({ business: { taxIdType: t.code } }).business.taxIdType).toBe(
				t.code
			);
		}
	});
});

describe('compatibilidad con las claves en español (T-113)', () => {
	/**
	 * Hasta el 2026-08-16 el JSON guardado usaba claves en español. Si
	 * `mergeSettings` solo entendiera las nuevas, actualizar el sistema le
	 * borraría al dueño su moneda, su tasa de impuesto y su logo sin decir nada
	 * —y la caja empezaría a cobrar con los valores de fábrica—.
	 */
	const VIEJA = {
		negocio: {
			nombre: 'Pulpería La Esquina',
			razon_social: 'Inversiones La Esquina S.A.',
			identificacion: '3-101-123456',
			tipo_identificacion: '02',
			telefono: '2222-3333',
			correo: 'ventas@laesquina.cr',
			direccion: 'San José',
			sitio_web: 'laesquina.cr'
		},
		moneda: {
			codigo: 'usd',
			simbolo: '$',
			decimales: 2,
			separador_miles: ',',
			separador_decimal: '.',
			simbolo_al_final: false,
			espacio: false
		},
		impuesto: { nombre: 'ISV', tasa: 0.04 },
		documento: {
			plantilla: 'moderna',
			color: '#B45309',
			mostrar_logo: false,
			mostrar_codigo: true,
			ancho_tiquete: 58,
			mensaje_gracias: 'Vuelva pronto',
			leyenda: 'Sin validez tributaria',
			notas: 'Pago a 30 días'
		},
		apariencia: { color_acento: '#7C3AED' },
		electronica: {
			activa: true,
			ambiente: 'produccion',
			actividad_economica: '471101',
			sucursal: '002',
			terminal: '00003',
			usuario_atv: 'atv@laesquina.cr'
		}
	};

	it('una fila guardada con las claves viejas se lee entera', () => {
		const s = mergeSettings(VIEJA);

		expect(s.business.name).toBe('Pulpería La Esquina');
		expect(s.business.legalName).toBe('Inversiones La Esquina S.A.');
		expect(s.business.taxId).toBe('3-101-123456');
		expect(s.business.taxIdType).toBe('02');
		expect(s.business.phone).toBe('2222-3333');
		expect(s.business.email).toBe('ventas@laesquina.cr');
		expect(s.business.address).toBe('San José');
		expect(s.business.website).toBe('laesquina.cr');

		expect(s.currency.code).toBe('USD');
		expect(s.currency.decimalSeparator).toBe('.');
		expect(s.currency.thousandsSeparator).toBe(',');

		// La que más duele si se pierde: cobraría al 13 % en vez de al 4 %.
		expect(s.tax.name).toBe('ISV');
		expect(s.tax.rate).toBe(0.04);

		expect(s.document.template).toBe('moderna');
		expect(s.document.color).toBe('#b45309');
		expect(s.document.showLogo).toBe(false);
		expect(s.document.showBarcode).toBe(true);
		expect(s.document.receiptWidth).toBe(58);
		expect(s.document.thanksMessage).toBe('Vuelva pronto');
		expect(s.document.legalNotice).toBe('Sin validez tributaria');
		expect(s.document.notes).toBe('Pago a 30 días');

		expect(s.appearance.accentColor).toBe('#7c3aed');

		expect(s.eInvoicing.enabled).toBe(true);
		expect(s.eInvoicing.environment).toBe('produccion');
		expect(s.eInvoicing.economicActivity).toBe('471101');
		expect(s.eInvoicing.branch).toBe('002');
		expect(s.eInvoicing.terminal).toBe('00003');
		expect(s.eInvoicing.atvUser).toBe('atv@laesquina.cr');
	});

	it('la clave nueva gana cuando están las dos', () => {
		// Pasa justo después de guardar por primera vez con la versión nueva: la
		// fila lleva las dos formas hasta que el backend reemplaza el JSON entero.
		const s = mergeSettings({ ...VIEJA, tax: { name: 'IVA', rate: 0.13 } });
		expect(s.tax.rate).toBe(0.13);
	});

	it('una fila mezclada no rompe nada', () => {
		const s = mergeSettings({ negocio: { nombre: 'Mixta' }, currency: { code: 'EUR' } });
		expect(s.business.name).toBe('Mixta');
		expect(s.currency.code).toBe('EUR');
		expect(s.tax.rate).toBe(0.13);
	});
});
