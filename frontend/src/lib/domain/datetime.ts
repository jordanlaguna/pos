/**
 * El formato en que las fechas viajan al backend.
 *
 * No es formateo de interfaz —eso vive en `$lib/ui/format`— sino parte del
 * contrato con la API, y por eso está en el dominio: lo usan las acciones del
 * servidor, nunca un componente.
 */

/**
 * `YYYY-MM-DDTHH:mm:ss` en hora **local**, sin sufijo `Z` ni desfase.
 *
 * Con `toISOString()` se enviaría UTC. El backend guarda las fechas en hora
 * local del servidor —el contenedor lleva `TZ` justo por eso, que fue el
 * defecto 8— y compara `sales.created_at` contra `cash_sessions.opened_at` para
 * armar el turno. Mezclar UTC con local en esa comparación parte el arqueo del
 * turno de noche en dos.
 *
 * Para las ventas ya no importa —desde el defecto 9 la hora la sella el
 * servidor y este campo se ignora—, pero sí para dar de alta un producto.
 */
export function toLocalIso(value: Date | string | null | undefined): string {
	const d = toDate(value) ?? new Date();
	const pad = (n: number) => String(n).padStart(2, '0');
	return (
		`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
		`T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
	);
}

function toDate(value: Date | string | null | undefined): Date | null {
	if (!value) return null;
	const d = value instanceof Date ? value : new Date(value);
	return Number.isNaN(d.getTime()) ? null : d;
}
