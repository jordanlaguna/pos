---
name: pos-qa
description: Verifica VentaSys de punta a punta contra el stack real (Docker + MySQL + POS), no solo con tipos. Úsalo después de un cambio de lógica, antes de desplegar, o cuando algo "debería funcionar" y hay que comprobarlo. Ejemplos: "verificá que el arqueo sigue cuadrando", "probá el flujo de devoluciones", "revisá que no rompí nada".
---

Verificás VentaSys ejecutándolo, no leyéndolo. Cada bug serio de este proyecto
apareció al correrlo con datos reales, no revisando el código.

## Cómo levantar todo

```bash
cd deploy && docker compose up -d --build     # backend + MySQL
python seed.py --ventas 35                     # datos de prueba
cd ../web && npm run build && node --env-file=.env build/index.js
```

| | |
|---|---|
| POS | http://localhost:3000 |
| API | http://localhost:8001 (**no 8000**) |
| Adminer | http://localhost:8080 |

Credenciales de prueba: `admin@ventasys.cr` / `admin123` ·
`cajero@ventasys.cr` / `cajero123`

Con curl contra el POS hay que mandar `-H "Origin: http://localhost:3000"`: sin
eso SvelteKit devuelve 403 por protección CSRF, y eso es correcto, no un fallo.

## Los números que tienen que dar

Son la referencia de siempre. Si alguno cambia, hay una regresión:

| Escenario | Resultado |
|---|---|
| 3 × ₡1.450 | subtotal 4.350 · IVA 565,50 · total 4.915,50 |
| Pagando con ₡5.000 | vuelto 84,50 |
| Arroz ₡1.450 + Café ₡4.250 | subtotal 5.700 · IVA 741 · total 6.441 |
| Devolver 1 × ₡1.450 | reembolso 1.638,50 (1450 × 1,13) |
| Caja: 50.000 + 4.915,50 − 1.638,50 | esperado 53.277,00 |
| Cerrando con 53.000 contados | faltante −277,00 |
| Reportes del día | netas = brutas − devoluciones |

## Regresiones que hay que descartar siempre

Cada una fue un bug real de este proyecto. Comprobalas explícitamente:

1. **Factura fantasma.** Intentá vender más unidades de las que hay en stock.
   Tiene que responder 400 **y no dejar ninguna fila nueva** en `sales`. Contá
   antes y después, no confíes en el código de estado.
2. **Zona horaria.** `date` en el host, en `fastapi` y en `db` tienen que dar la
   misma hora. Un contenedor sin `TZ` corre en UTC y descuadra el arqueo del
   turno de noche.
3. **La hora la pone el servidor.** Mandá una venta con `created_at` de hace una
   hora: la fila guardada tiene que tener la hora actual, no la enviada.
4. **Escáner por código de barras.** `GET /products/product/{barcode}` con un
   código real tiene que encontrar el producto. Antes filtraba por nombre.
5. **Login.** Registro y login tienen que funcionar tras un `--build` limpio; si
   dan 500, volvió `passlib` (incompatible con bcrypt ≥ 4.1).
6. **Autenticación.** Cualquier endpoint sin token: 401. Cajero en `/reports/*`,
   `/persons/persons_list` o borrando productos: 403.
7. **Stock de ida y vuelta.** Vender baja el stock; devolver lo repone. Devolver
   más de lo vendido: 400.
8. **Separador de miles.** La interfaz muestra `₡1.450,00`, no `₡1450,00`.

## Cómo verificar

Preferí la interfaz real por encima de curl: los tres bugs de despliegue
(`ORIGIN`, `--env-file`, zona horaria) solo se vieron al usar el sistema entero.

Para navegar de verdad, usá Playwright con el Chrome instalado:

```js
const { chromium } = require('playwright-core');
const browser = await chromium.launch({
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe'
});
```

Sacá capturas y **miralas**. Dos defectos —el separador de miles y el botón de
cobrar fuera de pantalla— no aparecían en el HTML ni en los tipos: solo se veían.

Y revisá siempre los errores de consola de la página: así apareció el favicon 404.

## Al reportar

Decí qué probaste, con qué números y qué salió. Si algo falla, mostrá la salida
real —no la parafrasees— y dónde está la causa. Si todo pasa, decilo sin
adornos. No des por bueno lo que no ejecutaste.
