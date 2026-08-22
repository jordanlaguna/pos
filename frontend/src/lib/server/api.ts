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

/**
 * Un «no» del backend, tal como viaja: código y datos, nunca una frase.
 *
 * La frase la arma `apiMessage()` en `$lib/ui/messages` (RN-30). Acá no se
 * escribe texto para nadie: `message` es para el registro, no para la pantalla.
 * El tipo está declarado suelto y no como la clase porque `$lib/ui` no puede
 * importar `$lib/server` —lo prohíbe SvelteKit, y con razón— y `ApiError` lo
 * cumple por estructura.
 */
export interface ApiFailure {
	readonly status: number;
	readonly code: string;
	readonly data: Readonly<Record<string, unknown>>;
}

export class ApiError extends Error implements ApiFailure {
	readonly status: number;
	readonly code: string;
	readonly data: Readonly<Record<string, unknown>>;

	constructor(status: number, code: string, data: Record<string, unknown> = {}) {
		// El mensaje técnico: es lo que sale en un `console.error` o en un
		// traceback, no lo que ve una persona.
		super(`${code} (HTTP ${status})`);
		this.name = 'ApiError';
		this.status = status;
		this.code = code;
		this.data = data;
	}

	/** Errores 4xx son culpa de quien pidió; 5xx, del servidor. */
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

/**
 * El código y los datos que trae un error del backend.
 *
 * La forma normal es `{"detail": {"code": "insufficient_stock", ...}}`. Las otras
 * dos son ajenas a nosotros y por eso quedan como códigos propios del POS:
 *
 * - **Un `detail` que es texto.** Lo produce Starlette por su cuenta —«Not
 *   Found» en una ruta que no existe, «Method Not Allowed»— y está en inglés.
 *   No se muestra: se registra y la pantalla dice lo suyo.
 * - **Un `detail` que es una lista.** Son los errores de validación de Pydantic,
 *   también en inglés y nombrando el campo de la base (`payment_method`). Se
 *   resumen en un código y el detalle queda en `data` para el registro.
 */
function extractFailure(payload: unknown): { code: string; data: Record<string, unknown> } {
	if (payload && typeof payload === 'object') {
		const detail = (payload as { detail?: unknown }).detail;

		if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
			const { code, ...data } = detail as { code?: unknown } & Record<string, unknown>;
			if (typeof code === 'string' && code) return { code, data };
			return { code: 'unexpected', data: { detail } };
		}

		if (Array.isArray(detail)) {
			const fields = detail
				.map((d) =>
					d && typeof d === 'object' && Array.isArray((d as { loc?: unknown[] }).loc)
						? (d as { loc: unknown[] }).loc.filter((p) => p !== 'body').join('.')
						: ''
				)
				.filter(Boolean);
			return { code: 'invalid_request', data: { fields, detail } };
		}

		if (typeof detail === 'string' && detail.trim()) {
			return { code: 'unexpected', data: { detail: detail.trim() } };
		}
	}
	return { code: 'unexpected', data: payload === null ? {} : { payload } };
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
		throw new ApiError(503, isTimeout ? 'timeout' : 'unreachable', {
			base: API_BASE_URL,
			ms: API_TIMEOUT_MS,
			cause: error
		});
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
		const { code, data } = extractFailure(payload);
		throw new ApiError(response.status, code, data);
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

/**
 * Lo que se registra de un fallo. **No** es lo que se le muestra a nadie.
 *
 * La frase para la pantalla la arma `apiMessage()` en `$lib/ui/messages`, con el
 * catálogo del idioma que corresponda.
 */
export function toLog(error: unknown): string {
	if (error instanceof ApiError) {
		return `${error.message} ${JSON.stringify(error.data)}`;
	}
	if (error instanceof Error) return `${error.name}: ${error.message}`;
	return String(error);
}
