import { describe, expect, it } from 'vitest';
import {
	DOCUMENT_STATES,
	STOP_REASONS,
	downloadable,
	isFinal,
	isPending,
	knownState,
	needsPerson
} from './transmission';

describe('el recorrido visto desde la pantalla', () => {
	it('conoce los siete estados y los diez motivos', () => {
		expect(DOCUMENT_STATES).toHaveLength(7);
		expect(new Set(STOP_REASONS).size).toBe(10);
	});

	it('distingue lo terminado, lo pendiente y lo que necesita a una persona', () => {
		expect(isFinal('accepted') && isFinal('rejected')).toBe(true);
		expect(isFinal('sent') || isFinal(null)).toBe(false);
		expect(
			(['numbered', 'signed', 'sent', 'retrying'] as const).every((s) => isPending(s))
		).toBe(true);
		expect(isPending('stopped') || isPending(undefined)).toBe(false);
		expect(needsPerson('stopped')).toBe(true);
		expect(needsPerson('retrying')).toBe(false);
	});

	it('un estado desconocido se trata como pendiente', () => {
		expect(knownState('accepted')).toBe('accepted');
		expect(knownState('volando')).toBe('numbered');
		expect(knownState(undefined)).toBe('numbered');
	});

	it('dice qué se puede bajar', () => {
		expect(downloadable(null)).toEqual({ xml: false, response: false });
		expect(downloadable({ has_xml: true } as never)).toEqual({ xml: true, response: false });
		expect(downloadable({ has_xml: true, has_response: true } as never)).toEqual({
			xml: true,
			response: true
		});
	});
});
