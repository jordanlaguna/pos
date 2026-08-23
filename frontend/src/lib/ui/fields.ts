/**
 * Rótulos de campo para los mensajes de validación (T-815).
 *
 * Cada campo declara **una vez** su texto y su concordancia gramatical, y las
 * acciones lo piden por nombre: `v.decimal('cash_received', F.cashReceived())`.
 * Antes cada llamada llevaba la cadena en español escrita a mano, repetida en
 * los sitios donde el mismo campo aparece en dos pantallas.
 *
 * **Son funciones, no constantes.** Una constante se evaluaría al importar el
 * módulo, o sea una vez por proceso de Node, y congelaría el idioma de la
 * primera petición para todas las demás: el defecto 17 otra vez. Llamándolas se
 * resuelven dentro de la petición.
 */

import type { FieldLabel } from '$lib/application/validation';
import { m } from '$lib/paraglide/messages.js';

const masculino = (text: string): FieldLabel => ({ text, concord: 'm' });
const femenino = (text: string): FieldLabel => ({ text, concord: 'f' });
const femeninoPlural = (text: string): FieldLabel => ({ text, concord: 'fp' });

export const F = {
	// ------------------------------------------------------------------ plata
	amount: () => masculino(m.field_amount()),
	cashReceived: () => masculino(m.field_cash_received()),
	closingAmount: () => masculino(m.field_closing_amount()),
	openingAmount: () => masculino(m.field_opening_amount()),
	price: () => masculino(m.field_price()),
	stock: () => masculino(m.field_stock()),
	taxRate: () => femenino(m.field_tax_rate()),
	taxName: () => masculino(m.field_tax_name()),
	decimals: () => femenino(m.field_decimals()),

	// ------------------------------------------------------------- catálogo
	name: () => masculino(m.field_name()),
	categoryName: () => masculino(m.field_category_name()),
	description: () => femenino(m.field_description()),
	barcode: () => masculino(m.field_barcode()),
	category: () => femenino(m.field_category()),
	notes: () => femeninoPlural(m.field_notes()),
	reason: () => masculino(m.field_reason()),

	// -------------------------------------------------------------- personas
	firstLastName: () => masculino(m.field_first_last_name()),
	secondLastName: () => masculino(m.field_second_last_name()),
	identification: () => femenino(m.field_identification()),
	telephone: () => masculino(m.field_telephone()),
	address: () => femenino(m.field_address()),
	email: () => masculino(m.field_email()),
	password: () => femenino(m.field_password()),
	role: () => masculino(m.field_role()),
	birthDate: () => femenino(m.field_birth_date()),
	registerDate: () => femenino(m.field_register_date()),

	// ----------------------------------------------------- referencias por id
	client: () => masculino(m.field_client()),
	person: () => femenino(m.field_person()),
	product: () => masculino(m.field_product()),
	user: () => masculino(m.field_user()),
	sale: () => femenino(m.field_sale()),
	entry: () => femenino(m.field_entry()),

	// ------------------------------------------------------------ conjuntos
	paymentMethod: () => masculino(m.field_payment_method()),
	movementType: () => masculino(m.field_movement_type()),

	// --------------------------------------------------------- configuración
	businessName: () => masculino(m.field_business_name()),
	businessLegalName: () => femenino(m.field_business_legal_name()),
	businessIdentification: () => femenino(m.field_business_identification()),
	businessIdType: () => masculino(m.field_business_id_type()),
	businessAddress: () => femenino(m.field_business_address()),
	businessTelephone: () => masculino(m.field_business_telephone()),
	businessEmail: () => masculino(m.field_business_email()),
	businessWebsite: () => masculino(m.field_business_website()),

	currencyCode: () => masculino(m.field_currency_code()),
	currencySymbol: () => masculino(m.field_currency_symbol()),

	documentTemplate: () => femenino(m.field_document_template()),
	documentWidth: () => masculino(m.field_document_width()),
	documentLegend: () => femenino(m.field_document_legend()),
	documentFarewell: () => masculino(m.field_document_farewell()),
	documentNotes: () => femeninoPlural(m.field_document_notes()),
	locale: () => masculino(m.field_locale()),
	documentLocale: () => masculino(m.field_document_locale()),

	einvoicingEnvironment: () => masculino(m.field_einvoicing_environment()),
	einvoicingActivity: () => femenino(m.field_einvoicing_activity()),
	einvoicingBranch: () => femenino(m.field_einvoicing_branch()),
	einvoicingTerminal: () => femenino(m.field_einvoicing_terminal()),
	einvoicingAtvUser: () => masculino(m.field_einvoicing_atv_user()),

	// ---------------------------------------------- panel de soporte (F3)
	companyName: () => masculino(m.field_company_name()),
	affiliate: () => masculino(m.field_affiliate()),
	companyNumber: () => masculino(m.field_company_number()),
	plan: () => masculino(m.field_plan()),
	companyState: () => masculino(m.field_company_state()),
	expiresOn: () => femenino(m.field_expires_on())
};
