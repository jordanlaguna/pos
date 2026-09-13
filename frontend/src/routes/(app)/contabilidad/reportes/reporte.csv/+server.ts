import { error } from '@sveltejs/kit';
import { apiSafe } from '$lib/server/api';
import { m } from '$lib/paraglide/messages.js';
import { entryTitle, kindLabel } from '$lib/ui/accounting';
import type {
	BalanceSheet,
	IncomeStatement,
	Journal,
	LedgerReport,
	TrialBalance
} from '$lib/domain/types';
import type { RequestHandler } from './$types';

/**
 * Los cinco libros en CSV.
 *
 * **El CSV lo arma el POS y no el backend**, y no es un capricho de reparto: un
 * CSV lleva encabezados, y los encabezados son texto que lee una persona
 * (RN-30). El backend devuelve las cifras; acá se les pone nombre en el idioma
 * de quien descarga. Es lo mismo que ya hace la plantilla de importación de
 * inventario.
 *
 * CSV y no Excel, como decidió plan §13.1: cualquier programa contable lo
 * importa y el POS no gana una dependencia.
 */

/** Una celda, escapada. La coma y las comillas son lo que rompe un CSV. */
function celda(valor: unknown): string {
	const texto = valor == null ? '' : String(valor);
	return /[",;\n]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto;
}

function filas(lineas: unknown[][]): string {
	return lineas.map((fila) => fila.map(celda).join(',')).join('\r\n');
}

export const GET: RequestHandler = async ({ locals, url }) => {
	if (!locals.user) error(401, { message: m.common_session_required() });

	const reporte = url.searchParams.get('report') ?? 'trial-balance';
	const year = Number(url.searchParams.get('year')) || new Date().getFullYear();
	const mesPedido = url.searchParams.get('month');
	const month = mesPedido ? Number(mesPedido) : null;
	const consulta = `year=${year}${month ? `&month=${month}` : ''}`;

	const datos = await apiSafe<unknown>(`/accounting/reports/${reporte}?${consulta}`, null, {
		token: locals.token
	});
	if (!datos) error(404, { message: m.accounting_report_empty() });

	let lineas: unknown[][] = [];

	if (reporte === 'trial-balance') {
		const balance = datos as TrialBalance;
		lineas = [
			[
				m.accounting_account_code(),
				m.accounting_account_name(),
				m.accounting_account_kind(),
				m.accounting_entry_debit(),
				m.accounting_entry_credit()
			],
			...balance.rows.map((fila) => [
				fila.code,
				fila.name,
				kindLabel(fila.kind),
				fila.debits,
				fila.credits
			]),
			[m.accounting_entry_total(), '', '', balance.debits, balance.credits]
		];
	} else if (reporte === 'income' || reporte === 'balance') {
		const estado = datos as IncomeStatement & BalanceSheet;
		lineas = [
			[
				m.accounting_account_code(),
				m.accounting_account_name(),
				m.accounting_account_kind(),
				m.accounting_entry_total()
			],
			...estado.rows.map((fila) => [fila.code, fila.name, kindLabel(fila.kind), fila.balance])
		];
	} else if (reporte === 'journal') {
		const diario = datos as Journal;
		lineas = [
			[
				m.accounting_entry_number(),
				m.accounting_entry_date(),
				m.accounting_entry_description(),
				m.accounting_account_code(),
				m.accounting_account_name(),
				m.accounting_entry_debit(),
				m.accounting_entry_credit()
			],
			...diario.entries.flatMap((asiento) =>
				(asiento.lines ?? []).map((linea) => [
					asiento.entry_number,
					asiento.entry_date,
					entryTitle(asiento),
					linea.account_code,
					linea.account_name,
					linea.debit,
					linea.credit
				])
			)
		];
	} else {
		const mayor = datos as LedgerReport;
		lineas = [
			[
				m.accounting_account_code(),
				m.accounting_account_name(),
				m.accounting_ledger_opening(),
				m.accounting_entry_date(),
				m.accounting_entry_number(),
				m.accounting_entry_debit(),
				m.accounting_entry_credit(),
				m.accounting_ledger_closing()
			],
			...mayor.accounts.flatMap((cuenta) =>
				cuenta.movements.map((movimiento) => [
					cuenta.code,
					cuenta.name,
					cuenta.opening,
					movimiento.entry_date,
					movimiento.entry_number,
					movimiento.debit,
					movimiento.credit,
					cuenta.closing
				])
			)
		];
	}

	const periodo = month ? `${year}-${String(month).padStart(2, '0')}` : String(year);
	// El BOM hace que Excel abra el archivo en UTF-8 y no rompa las tildes.
	return new Response('﻿' + filas(lineas), {
		headers: {
			'content-type': 'text/csv; charset=utf-8',
			'content-disposition': `attachment; filename="${reporte}-${periodo}.csv"`
		}
	});
};
