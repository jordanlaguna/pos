/**
 * El recorrido de un comprobante hasta Hacienda, visto desde la pantalla
 * (F7, RN-39 a RN-42).
 *
 * Las reglas de verdad viven en el backend (`domain/fe_transmission.py`); acá
 * solo lo que la pantalla necesita para decidir qué enseñar: si un estado ya
 * terminó, si necesita a una persona, y qué se puede bajar.
 */

import type { DocumentState, EmittedDocument, StopReason } from './types';

export const DOCUMENT_STATES: readonly DocumentState[] = [
	'numbered',
	'signed',
	'sent',
	'accepted',
	'rejected',
	'retrying',
	'stopped'
];

export const STOP_REASONS: readonly StopReason[] = [
	'certificate_missing',
	'certificate_expired',
	'credentials_missing',
	'credentials_rejected',
	'document_invalid',
	'reception_rejected',
	'forbidden',
	'hacienda_error',
	'retries_exhausted',
	'no_verdict'
];

/** Hacienda ya contestó: no se mueve más. */
export function isFinal(state: DocumentState | null | undefined): boolean {
	return state === 'accepted' || state === 'rejected';
}

/** Lo que la cola todavía mueve sola. */
export function isPending(state: DocumentState | null | undefined): boolean {
	return state === 'numbered' || state === 'signed' || state === 'sent' || state === 'retrying';
}

/** Lo que necesita a una persona (RF-35). */
export function needsPerson(state: DocumentState | null | undefined): boolean {
	return state === 'stopped';
}

/** Un estado que la pantalla no conoce se trata como pendiente: nunca se esconde. */
export function knownState(value: unknown): DocumentState {
	return (DOCUMENT_STATES as readonly string[]).includes(String(value))
		? (value as DocumentState)
		: 'numbered';
}

/** Qué archivos del expediente existen para bajar (RF-34). */
export function downloadable(doc: EmittedDocument | null | undefined): {
	xml: boolean;
	response: boolean;
} {
	return { xml: Boolean(doc?.has_xml), response: Boolean(doc?.has_response) };
}
