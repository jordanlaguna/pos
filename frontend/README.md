# VentaSys — Punto de venta

Frontend del sistema de ventas, migrado de **C# / Windows Forms** a **SvelteKit**.
Consume el backend FastAPI del repositorio `backend-python`.

---

## Arranque rápido

```bash
npm install
cp .env.example .env    # y editá API_BASE_URL con la IP de tu VM
npm run dev
```

Abrí <http://localhost:5173>.

### Probarlo sin backend

Con `POS_MOCK=1` en el `.env` el sistema sirve un backend simulado en memoria,
con 26 productos, 45 días de ventas de ejemplo y datos de caja. No toca la red.

| Usuario | Contraseña | Rol |
|---|---|---|
| `admin@ventasys.cr` | `admin123` | Administrador |
| `cajero@ventasys.cr` | `cajero123` | Cajero |

Los datos se guardan en `.data/mock-db.json`. Borrá ese archivo para volver al
estado de fábrica.

### Conectar la VM

```bash
# .env
API_BASE_URL=http://192.168.1.50:8001
POS_MOCK=0
```

**El puerto es 8001, no 8000.** En el `docker-compose` FastAPI escucha en el
puerto 80 dentro del contenedor y se publica en el 8001 de la VM (`"8001:80"`).

El backend que sirve todo esto está en [`../backend/`](../backend/) y se levanta
solo con `docker compose up -d --build`. Contra un FastAPI más viejo el POS
arranca igual, pero las secciones que dependen de endpoints que no existen
—caja, devoluciones, reportes, entradas— lo avisan en pantalla en vez de fallar.

---

## Variables de entorno

| Variable | Por defecto | Para qué sirve |
|---|---|---|
| `API_BASE_URL` | `http://localhost:8000` | URL del FastAPI. Con Docker, puerto **8001**. |
| `POS_MOCK` | — | `1` activa el backend simulado. |
| `API_TIMEOUT_MS` | `8000` | Corte por petición. Un backend colgado no congela la caja. |
| `LOW_STOCK_THRESHOLD` | `10` | Umbral de las alertas de inventario. |
| `POS_INSECURE_COOKIE` | — | `1` permite la cookie de sesión sin HTTPS en producción. |
| `ORIGIN` | — | **Obligatoria en producción.** URL pública del POS. |
| `PORT` | `3000` | Puerto en el que escucha el build de producción. |

Se leen **en tiempo de ejecución**, no de build: apuntar el POS a otra VM es
editar el `.env` y reiniciar, sin recompilar.

---

## Desplegar

```bash
npm run build
node --env-file=.env build/index.js
```

Dos cosas que hacen falta y no son evidentes:

**`node build/index.js` no lee el `.env`.** Vite lo carga en desarrollo; el build
de producción es Node a secas y solo ve variables del proceso. De ahí el
`--env-file=.env` (Node 20.6+). Si no, `API_BASE_URL` cae al valor por defecto y
el POS busca el backend en `localhost:8000` aunque el `.env` diga otra cosa.

**`ORIGIN` es obligatoria.** adapter-node la usa para validar el origen de los
formularios. Sin ella, todo POST responde `403 Cross-site POST form submissions
are forbidden` y no se puede ni iniciar sesión ni cobrar. Tiene que coincidir con
la URL por la que entran los cajeros: si escriben `http://192.168.1.60:3000`,
`ORIGIN` es exactamente eso.

Para que arranque solo al encender la máquina, con systemd:

```ini
# /etc/systemd/system/ventasys.service
[Unit]
Description=VentaSys POS
After=network.target

[Service]
Type=simple
User=ventasys
WorkingDirectory=/opt/ventasys/web
ExecStart=/usr/bin/node --env-file=.env build/index.js
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now ventasys
```

---

## Qué hay en cada pantalla

| Ruta | Rol | Descripción |
|---|---|---|
| `/ventas` | todos | Caja: escáner, grilla táctil por categoría, carrito, cobro. `F1` cobra, `F2` enfoca el buscador. |
| `/caja` | todos | Apertura de turno, entradas y salidas de efectivo, cierre con arqueo y diferencia. |
| `/facturas` | todos | Historial con filtros; el detalle es un ticket imprimible. |
| `/devoluciones` | todos | Devolución total o parcial de una venta; repone el stock. |
| `/dashboard` | admin | Ventas netas, ticket promedio, tendencia diaria, productos más vendidos, métodos de pago y alertas de stock. |
| `/inventario` | admin | Alta, edición y baja de productos; categorías; alertas de stock bajo. |
| `/clientes` | todos | Registro y edición de clientes. |
| `/usuarios` | admin | Datos de las personas y cambio de rol. |

---

## Decisiones de diseño

### El JWT vive en una cookie httpOnly

El WinForms guardaba el token en una clase estática (`AuthSession`). Aquí la
sesión vive en una cookie `httpOnly` + `sameSite=strict`: ningún script del
navegador puede leerla. Todas las llamadas al backend salen del **servidor** de
SvelteKit, así que el navegador nunca ve la IP de la VM y no hay CORS que
configurar.

### Los precios se recalculan en el servidor

La acción de cobro relee el catálogo del backend y recalcula subtotal, IVA y
total con esos precios. Lo que manda el navegador son solo identificadores de
producto y cantidades; un carrito manipulado no puede cambiar lo que se cobra.

### La aritmética redondea en cada paso

`decimal` de C# es exacto en base 10; `number` de JavaScript no. Un carrito
largo acumula centavos fantasma, así que `$lib/money.ts` redondea a 2 decimales
en cada operación, igual que hacía el original al escribir `.ToString("0.00")`
en la grilla.

### No se vende con la caja cerrada

Una venta que no pertenece a ningún turno no aparece en ningún arqueo. La
pantalla de ventas lo bloquea y ofrece abrir la caja en el momento, sin cambiar
de sección.

### El carrito sobrevive a un refresco

Vive en `sessionStorage`. Si el navegador se recarga a media compra, las líneas
siguen ahí. El WinForms perdía la venta entera al cerrar el formulario.

### El ticket se imprime desde el navegador

Reemplaza el PDF de iTextSharp: `@media print` deja la hoja sola en la página y
el navegador ofrece «Guardar como PDF». El PDF que genera el backend con
ReportLab sigue disponible en el botón «PDF del backend».

### Los gráficos son de serie única

Tendencia y magnitudes usan un solo tono (`#0891b2`), validado para banda de
luminosidad, piso de croma y contraste ≥3:1 contra las superficies clara y
oscura. La longitud codifica el valor; teñir cada barra según su tamaño gastaría
el canal de color en información que la barra ya muestra. Cada gráfico tiene su
gemela en tabla, así que ningún dato depende del color ni del puntero.

---

## Comandos

```bash
npm run dev       # desarrollo
npm run check     # verificación de tipos (svelte-check)
npm run build     # build de producción (adapter-node)
npm run preview   # previsualizar el build
```

Para desplegarlo:

```bash
npm run build
node build/index.js    # escucha en el puerto 3000 por defecto
```

---

## Estructura

```
src/
├── lib/
│   ├── components/       # Icon, Modal, Field, StatCard, Toaster…
│   │   └── charts/       # ChartCard, SalesTrendChart, BarListChart
│   ├── server/           # solo servidor: nunca llega al navegador
│   │   ├── api.ts        # cliente HTTP hacia FastAPI
│   │   ├── auth.ts       # sesión, cookie y guardas de rol
│   │   ├── config.ts     # variables de entorno
│   │   └── mock/         # backend simulado
│   ├── stores/           # cart, toast, theme (runes de Svelte 5)
│   ├── money.ts          # aritmética monetaria e IVA
│   ├── format.ts         # fechas y textos en es-CR
│   ├── types.ts          # modelo de dominio
│   └── validation.ts     # validación de formularios en el servidor
├── routes/
│   ├── login/ registro/  # públicas
│   └── (app)/            # exigen sesión iniciada
└── hooks.server.ts       # resuelve la sesión una vez por petición
```
