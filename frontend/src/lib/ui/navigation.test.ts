import { describe, expect, it } from 'vitest';
import { visibleGroups } from './navigation';
import { MODULES, type ModuleName } from '$lib/domain/types';

/**
 * El menú para un rol y para los módulos del plan (RN-49).
 *
 * Lo que se prueba acá no es qué secciones hay —eso cambia con cada fase— sino
 * las dos reglas que no pueden cambiar sin que alguien lo decida:
 *
 * 1. Lo que no se puede abrir **se muestra con candado, no desaparece**.
 *    Esconderlo hizo creer a un cajero que el sistema no tenía inventario, y
 *    para un módulo esconde además lo que se quiere vender.
 * 2. El candado **dice por qué**. Las dos razones se arreglan de maneras
 *    opuestas —una pidiendo un cambio de rol, la otra subiendo de plan— y el
 *    menú llegó a decirle a un administrador «solo para administradores».
 */

function buscar(role: 'admin' | 'cajero', modules: Record<string, boolean> | null, href: string) {
	for (const grupo of visibleGroups(role, modules as never)) {
		const item = grupo.items.find((i) => i.href === href);
		if (item) return item;
	}
	throw new Error(`no está ${href} en el menú`);
}

/** Un plan con estos módulos encendidos y el resto apagados (QA-01). */
function plan(...encendidos: ModuleName[]): Record<ModuleName, boolean> {
	return Object.fromEntries(MODULES.map((m) => [m, encendidos.includes(m)])) as Record<ModuleName, boolean>;
}

const CON_COMPRAS = plan(...MODULES);
/** La base del POS sin nada de lo que se vende aparte. */
const SIN_MODULOS = plan('sales', 'cash', 'invoices', 'returns', 'reports', 'inventory', 'clients', 'users');
const COMPRAS = '/compras/cuentas-por-pagar';

describe('el menú no esconde lo que no se puede abrir', () => {
	it('una sección de administrador se ve para un cajero, bloqueada', () => {
		const item = buscar('cajero', CON_COMPRAS, '/inventario');
		expect(item.locked).toBe(true);
		expect(item.lockedBy).toBe('role');
	});

	it('y sin candado para quien sí puede', () => {
		const item = buscar('admin', CON_COMPRAS, '/inventario');
		expect(item.locked).toBe(false);
		expect(item.lockedBy).toBeUndefined();
	});
});

describe('un módulo que el plan no incluye', () => {
	it('se ve con candado y dice que es del plan, no del rol', () => {
		const item = buscar('admin', SIN_MODULOS, COMPRAS);
		expect(item.locked).toBe(true);
		// La distinción que costó un mensaje falso: a un administrador se le
		// estaba diciendo que pidiera un cambio de rol.
		expect(item.lockedBy).toBe('module');
	});

	it('con el módulo en el plan, se abre', () => {
		expect(buscar('admin', CON_COMPRAS, COMPRAS).locked).toBe(false);
	});

	it('sin módulos conocidos se trata como si no estuviera', () => {
		// Es lo que pasa mientras el backend no manda `modules`: se prefiere el
		// candado a dejar entrar, porque el «no» de verdad está en el servidor y
		// un menú abierto solo lleva a un 403.
		expect(buscar('admin', null, COMPRAS).locked).toBe(true);
	});

	it('al cajero le gana el rol sobre el plan', () => {
		// Las dos razones a la vez. Se dice la del rol porque cambiar de plan no
		// le serviría de nada: seguiría sin poder entrar.
		const item = buscar('cajero', SIN_MODULOS, COMPRAS);
		expect(item.lockedBy).toBe('role');
	});
});

describe('los paquetes (QA-01)', () => {
	it('un restaurante ve la caja con candado del plan', () => {
		const restaurante = plan('sales', 'invoices', 'clients', 'users');
		const caja = buscar('admin', restaurante, '/caja');
		expect([caja.locked, caja.lockedBy]).toEqual([true, 'module']);
		expect(buscar('admin', restaurante, '/ventas').locked).toBe(false);
	});

	it('proveedores es su propia entrada: Comercio la tiene sin compras', () => {
		const comercio = plan('sales', 'cash', 'invoices', 'returns', 'inventory', 'suppliers', 'clients', 'users');
		expect(buscar('admin', comercio, '/compras/proveedores').locked).toBe(false);
		expect(buscar('admin', comercio, COMPRAS).lockedBy).toBe('module');
	});

	it('configuración no es un módulo: ningún plan la cierra', () => {
		expect(buscar('admin', plan(), '/configuracion').locked).toBe(false);
	});
});
