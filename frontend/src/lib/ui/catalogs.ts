/**
 * Los rótulos de las listas cerradas: monedas y plantillas de documento.
 *
 * Estas listas viven en `$lib/domain/settings` como **códigos** —el ISO 4217 de
 * la moneda, el id de la plantilla— porque son lo que se guarda. El nombre para
 * una persona vive acá, que es la interfaz, y sale del catálogo del idioma.
 *
 * Son funciones y no constantes por lo de siempre: una constante de módulo se
 * evalúa una vez por proceso, y en el servidor todas las peticiones verían el
 * idioma de la primera (el defecto 17).
 */

import type { TemplateId } from '$lib/domain/settings';
import { m } from '$lib/paraglide/messages.js';

/** Nombre de la moneda. Si no la conocemos, el código dice bastante. */
export function currencyName(code: string): string {
	switch (code) {
		case 'CRC':
			return m.settings_currency_CRC();
		case 'USD':
			return m.settings_currency_USD();
		case 'EUR':
			return m.settings_currency_EUR();
		case 'MXN':
			return m.settings_currency_MXN();
		case 'GTQ':
			return m.settings_currency_GTQ();
		case 'HNL':
			return m.settings_currency_HNL();
		case 'NIO':
			return m.settings_currency_NIO();
		case 'PAB':
			return m.settings_currency_PAB();
		case 'DOP':
			return m.settings_currency_DOP();
		case 'COP':
			return m.settings_currency_COP();
		case 'PEN':
			return m.settings_currency_PEN();
		case 'CLP':
			return m.settings_currency_CLP();
		case 'ARS':
			return m.settings_currency_ARS();
		default:
			return code;
	}
}

export interface TemplateLabels {
	name: string;
	/** Papel para el que está pensada. */
	paper: string;
	description: string;
}

/** Cómo se presenta una plantilla en el selector de Configuración. */
export function templateInfo(id: TemplateId): TemplateLabels {
	switch (id) {
		case 'clasica':
			return {
				name: m.settings_template_classic_name(),
				paper: m.settings_template_classic_paper(),
				description: m.settings_template_classic_description()
			};
		case 'moderna':
			return {
				name: m.settings_template_modern_name(),
				paper: m.settings_template_modern_paper(),
				description: m.settings_template_modern_description()
			};
		case 'tiquete':
			return {
				name: m.settings_template_receipt_name(),
				paper: m.settings_template_receipt_paper(),
				description: m.settings_template_receipt_description()
			};
	}
}
