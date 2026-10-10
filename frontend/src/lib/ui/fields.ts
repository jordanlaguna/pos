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
const masculinoPlural = (text: string): FieldLabel => ({ text, concord: 'mp' });

export const F = {
	// ------------------------------------------------------------------ plata
	amount: () => masculino(m.field_amount()),
	cashReceived: () => masculino(m.field_cash_received()),
	closingAmount: () => masculino(m.field_closing_amount()),
	openingAmount: () => masculino(m.field_opening_amount()),
	price: () => masculino(m.field_price()),
	stock: () => masculino(m.field_stock()),
	taxRate: () => femenino(m.field_tax_rate()),
	decimals: () => femenino(m.field_decimals()),

	// ------------------------------------------------------------- catálogo
	name: () => masculino(m.field_name()),
	categoryName: () => masculino(m.field_category_name()),
	description: () => femenino(m.field_description()),
	barcode: () => masculino(m.field_barcode()),
	cabysCode: () => masculino(m.field_cabys_code()),
	category: () => femenino(m.field_category()),
	notes: () => femeninoPlural(m.field_notes()),
	reason: () => masculino(m.field_reason()),

	// -------------------------------------------------------------- personas
	firstLastName: () => masculino(m.field_first_last_name()),
	secondLastName: () => masculino(m.field_second_last_name()),
	identification: () => femenino(m.field_identification()),
	telephone: () => masculino(m.field_telephone()),
	address: () => femenino(m.field_address()),
	foreignAddress: () => femenino(m.field_foreign_address()),
	tariffHeading: () => femenino(m.field_tariff_heading()),
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
	// F15: las salidas con motivo y su catálogo.
	exit: () => femenino(m.field_exit()),
	quantity: () => femenino(m.field_quantity()),
	stockReason: () => masculino(m.field_stock_reason()),
	reasonCode: () => masculino(m.field_reason_code()),

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
	// Las credenciales de Hacienda (F6). El archivo y el PIN existen durante una
	// petición y no vuelven a existir; acá solo se nombran para el «no».
	certificateFile: () => masculino(m.field_certificate_file()),
	certificatePin: () => masculino(m.field_certificate_pin()),
	atvUser: () => masculino(m.field_atv_user()),
	atvPassword: () => femenino(m.field_atv_password()),
	// Sucursales y cajas (T-608). El código va aparte del nombre porque el «no»
	// que da el backend es distinto: el nombre está vacío, el código no cabe.
	branch: () => femenino(m.field_branch()),
	branchCode: () => masculino(m.field_branch_code()),
	terminalCode: () => masculino(m.field_terminal_code()),
	officeName: () => masculino(m.field_office_name()),

	// ---------------------------------------------- panel de soporte (F3)
	companyName: () => masculino(m.field_company_name()),
	affiliate: () => masculino(m.field_affiliate()),
	companyNumber: () => masculino(m.field_company_number()),
	plan: () => masculino(m.field_plan()),
	company: () => femenino(m.field_company()),
	terminal: () => femenino(m.field_terminal()),
	lastSequence: () => masculino(m.field_last_sequence()),
	companyState: () => masculino(m.field_company_state()),
	expiresOn: () => femenino(m.field_expires_on()),

	// ------------------------------------------------------ contabilidad (F11)
	accountingStartDate: () => femenino(m.field_accounting_start_date()),
	account: () => femenino(m.field_account()),
	accountCode: () => masculino(m.field_account_code()),
	accountKind: () => masculino(m.field_account_kind()),
	entryDate: () => femenino(m.field_entry_date()),

	// ---------------------------------------------------------- planilla (F12)
	employerNumber: () => masculino(m.field_employer_number()),
	scheduleName: () => masculino(m.field_schedule_name()),
	hoursPerDay: () => femeninoPlural(m.field_hours_per_day()),
	workdaysPerWeek: () => masculinoPlural(m.field_workdays_per_week()),
	firstCutDay: () => masculino(m.field_first_cut_day()),
	cutWeekday: () => masculino(m.field_cut_weekday()),
	seriesStart: () => masculino(m.field_series_start()),
	positionName: () => masculino(m.field_position_name()),
	ccssCode: () => masculino(m.field_ccss_code()),
	insCode: () => masculino(m.field_ins_code()),
	policyNumber: () => masculino(m.field_policy_number()),
	rtRate: () => femenino(m.field_rt_rate()),
	firstName: () => masculino(m.field_first_name()),
	lastName1: () => masculino(m.field_last_name_1()),
	hiredOn: () => femenino(m.field_hired_on()),
	periodSalary: () => masculino(m.field_period_salary()),
	validFrom: () => femenino(m.field_valid_from()),
	startsOn: () => femenino(m.field_starts_on()),
	endsOn: () => femenino(m.field_ends_on()),
	hours: () => femeninoPlural(m.field_hours()),
	days: () => masculinoPlural(m.field_days()),
	totalAmount: () => masculino(m.field_total_amount()),
	newSalary: () => masculino(m.field_new_salary()),
	memo: () => femenino(m.field_memo()),
	cutDate: () => femenino(m.field_cut_date()),
	payDate: () => femenino(m.field_pay_date()),
	year: () => masculino(m.field_year()),
	month: () => masculino(m.field_month()),
	terminatedOn: () => femenino(m.field_terminated_on()),
	asOf: () => femenino(m.field_as_of()),
	employee: () => masculino(m.field_employee()),
	kind: () => masculino(m.field_kind()),
	dependentChildren: () => masculinoPlural(m.field_dependent_children())
};
