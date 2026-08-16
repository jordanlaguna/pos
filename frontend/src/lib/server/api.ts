import { API_BASE_URL, API_TIMEOUT_MS, USE_MOCK } from './config';
import { mockRequest } from './mock/handler';

/**
 * Cliente HTTP hacia el backend FastAPI.
 *
 * Corre solo en el servidor de SvelteKit, nunca en el navegador. Eso da tres cosas
 * que el cliente WinForms no tenía: el JWT vive en una cookie httpOnly (inalcanzable
 * para cualquier script), no hay CORS que configurar contra la VM, y el navegador
 * jamás ve la IP del backend.
 */

export class ApiError extends Error {
	readonly status: number;
	readonly detail: unknown;

	constructor(status: number, message: string, detail?: unknown) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
		this.detail = detail;
	}

	/** Errores 4xx son culpa del usuario y su mensaje se le puede mostrar tal cual. */
	get isClientError(): boolean {
		return this.status >= 400 && this.status < 500;
	}
}

export interface ApiOptions {
	method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
	body?: unknown;
	token?: string | null;
	/** Query string ya normalizado. */
	query?: Record<string, string | number | boolean | null | undefined>;
	signal?: AbortSignal;
}

/** FastAPI devuelve los errores como `{"detail": ...}`. Lo aplanamos a texto. */
function extractDetail(payload: unknown, fallback: string): string {
	if (typeof payload === 'string' && payload.trim()) return payload.trim();
	if (payload && typeof payload === 'object') {
		const detail = (payload as { detail?: unknown }).detail;
		if (typeof detail === 'string' && detail.trim()) return detail.trim();
		// Errores de validación de Pydantic: [{loc, msg, type}, ...]
		if (Array.isArray(detail)) {
			const messages = detail
				.map((d) => {
					if (d && typeof d === 'object') {
						const loc = Array.isArray((d as { loc?: unknown[] }).loc)
							? (d as { loc: unknown[] }).loc.filter((p) => p !== 'body').join('.')
							: '';
						const msg = String((d as { msg?: unknown }).msg ?? '');
						return loc ? `${loc}: ${msg}` : msg;
					}
					return String(d);
				})
				.filter(Boolean);
			if (messages.length) return messages.join(' · ');
		}
		const message = (payload as { message?: unknown }).message;
		if (typeof message === 'string' && message.trim()) return message.trim();
	}
	return fallback;
}

function buildUrl(path: string, query?: ApiOptions['query']): string {
	const normalized = path.startsWith('/') ? path : `/${path}`;
	if (!query) return normalized;
	const params = new URLSearchParams();
	for (const [key, value] of Object.entries(query)) {
		if (value !== null && value !== undefined && value !== '') params.set(key, String(value));
	}
	const qs = params.toString();
	return qs ? `${normalized}?${qs}` : normalized;
}

/**
 * Ejecuta una petición contra el backend y devuelve el cuerpo ya deserializado.
 * Lanza ApiError en cualquier respuesta no 2xx, o si el backend no responde.
 */
export async function api<T = unknown>(path: string, options: ApiOptions = {}): Promise<T> {
	const { method = 'GET', body, token, query, signal } = options;
	const url = buildUrl(path, query);

	if (USE_MOCK) {
		return (await mockRequest<T>({ method, path: url, body, token })) as T;
	}

	const headers: Record<string, string> = { Accept: 'application/json' };
	if (body !== undefined) headers['Content-Type'] = 'application/json';
	if (token) headers['Authorization'] = `Bearer ${token}`;

	// AbortSignal.any encadena el timeout con la cancelación del propio request de Kit.
	const timeout = AbortSignal.timeout(API_TIMEOUT_MS);
	const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;

	let response: Response;
	try {
		response = await fetch(`${API_BASE_URL}${url}`, {
			method,
			headers,
			body: body === undefined ? undefined : JSON.stringify(body),
			signal: combined
		});
	} catch (error) {
		const isTimeout = error instanceof DOMException && error.name === 'TimeoutError';
		throw new ApiError(
			503,
			isTimeout
				? `El backend no respondió en ${API_TIMEOUT_MS} ms (${API_BASE_URL}).`
				: `No se pudo conectar con el backend en ${API_BASE_URL}.`,
			error
		);
	}

	const text = await response.text();
	let payload: unknown = null;
	if (text) {
		try {
			payload = JSON.parse(text);
		} catch {
			payload = text;
		}
	}

	if (!response.ok) {
		throw new ApiError(
			response.status,
			extractDetail(payload, `El backend respondió ${response.status}.`),
			payload
		);
	}

	return payload as T;
}

/**
 * Variante tolerante: devuelve `fallback` en vez de lanzar. Se usa en el dashboard,
 * donde un widget caído no debe tumbar la pantalla entera.
 */
export async function apiSafe<T>(
	path: string,
	fallback: T,
	options: ApiOptions = {}
): Promise<T> {
	try {
		return await api<T>(path, options);
	} catch {
		return fallback;
	}
}

/** Convierte cualquier excepción en un mensaje presentable en español. */
export function toMessage(error: unknown): string {
	if (error instanceof ApiError) return error.message;
	if (error instanceof Error) return error.message;
	return 'Ocurrió un error inesperado.';
}
