// Captura el POS con el menú desplegado y plegado, para revisar el tirador.
import { chromium } from '@playwright/test';

const BASE = 'http://localhost:5174';
const OUT = process.argv[2] ?? '.';

const navegador = await chromium.launch();
const pagina = await navegador.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 3 });

await pagina.goto(`${BASE}/login`);
await pagina.locator('input[name="email"]').fill('admin@ventasys.cr');
await pagina.locator('input[name="password"]').fill('admin123');
await pagina.getByRole('button', { name: /^entrar$/i }).click();
await pagina.waitForURL(/\/(ventas|dashboard|compania)/, { timeout: 20000 });
if (pagina.url().includes('/compania')) {
	await pagina.getByRole('button').first().click();
	await pagina.waitForURL(/\/(ventas|dashboard)/, { timeout: 20000 });
}

await pagina.goto(`${BASE}/ventas`);
await pagina.waitForTimeout(1500);
await pagina.screenshot({ path: `${OUT}/1-desplegado.png` });
await pagina.screenshot({ path: `${OUT}/zoom-desplegado.png`, clip: { x: 190, y: 20, width: 120, height: 80 } });

// El tirador vive en el borde del menú; se pulsa hasta que Svelte hidrate.
const tirador = pagina.locator('nav button[aria-label]').first();
for (let intento = 0; intento < 10; intento++) {
	await tirador.click();
	await pagina.waitForTimeout(400);
	const ancho = await pagina.locator('nav').first().evaluate((n) => n.getBoundingClientRect().width);
	if (ancho < 100) break;
}
await pagina.waitForTimeout(600);
await pagina.screenshot({ path: `${OUT}/zoom-plegado.png`, clip: { x: 20, y: 20, width: 120, height: 80 } });
await pagina.screenshot({ path: `${OUT}/2-plegado.png` });

await navegador.close();
console.log('listo');
