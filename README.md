# VentaSys

Punto de venta para comercio: ventas, caja, inventario, devoluciones, clientes y
reportes. Interfaz en español de Costa Rica, con voseo.

```
pos/
├── frontend/       ← el POS (SvelteKit 2 + Svelte 5 + Tailwind 4)
├── backend/        ← la API (FastAPI + MySQL 8). Se levanta sola con Docker.
├── .specify/       ← hacia dónde va el proyecto: spec, plan y tareas
└── docs/           ← material de referencia
```

## Probarlo sin backend

```bash
cd frontend && npm install && npm run dev
```

Viene con `POS_MOCK=1`: arranca con datos de ejemplo y sin tocar la red. Entrá
con `admin@ventasys.cr` / `admin123`.

## Levantarlo completo

```bash
cd backend
cp .env.example .env          # editá contraseñas, SECRET_KEY y TZ
docker compose up -d --build  # API en :8001, Adminer en :8080
python seed.py --ventas 35    # datos de prueba

cd ../frontend
# en .env: API_BASE_URL=http://IP_DE_LA_VM:8001, POS_MOCK=0, ORIGIN=…
npm run build && node --env-file=.env build/index.js
```

Tres cosas que cuestan una tarde si no se saben:

- **El puerto es 8001, no 8000** — el compose publica `"8001:80"`.
- **`node build/index.js` no lee el `.env`** — de ahí el `--env-file`. Sin eso el
  POS busca el backend en `localhost:8000` aunque el archivo diga otra cosa.
- **`ORIGIN` es obligatoria en producción** — sin ella todo formulario responde
  `403` y no se puede ni iniciar sesión.

Detalles en [`frontend/README.md`](frontend/README.md) y
[`backend/README.md`](backend/README.md).

---

## Qué hace

**Ventas.** Grilla táctil por categorías y lector de código de barras, con
atajos de teclado. Varias ventas en espera a la vez: si un cliente se va a
buscar otro producto, su venta queda en una pestaña y se atiende al siguiente.
Las existencias se validan contra lo apartado en todas las ventas abiertas.

**Caja.** Apertura de turno, entradas y salidas de efectivo, cierre con arqueo y
la diferencia contra lo esperado. No se vende con la caja cerrada: una venta que
no pertenece a ningún turno no aparece en ningún arqueo.

**Inventario.** Catálogo y recepción de mercadería por tres vías: manual, Excel
o CSV, y XML de factura electrónica de Hacienda (v4.3 y v4.4). Nada toca las
existencias hasta que se confirma la vista previa.

**Devoluciones.** Totales o parciales, con reposición de existencias. Cada
devolución usa la tasa de impuesto con la que se cobró su venta.

**Configuración.** Moneda, impuesto, datos del negocio, logo, colores y tres
plantillas de documento: tiquete térmico de 58 u 80 mm y dos facturas de página
completa.

**Reportes.** Ventas netas, ticket promedio, tendencia diaria, productos más
vendidos, desglose por método de pago y alertas de existencias bajas.

**Roles.** Administrador y cajero, aplicados en el servidor. Las secciones
restringidas se muestran con candado en vez de desaparecer: un cajero tiene que
entender que le falta permiso, no creer que el sistema no tiene inventario.

## De dónde viene

Es la migración de un POS en C#/WinForms sobre un backend FastAPI. Durante el
trabajo aparecieron **diez defectos** en el backend original —varios visibles
solo al ejecutarlo, como que los contenedores corrían en UTC y partían en dos el
arqueo del turno de noche—. Están explicados en
[`backend/README.md`](backend/README.md); las decisiones y los números de
referencia que deben cuadrar, en `.specify/progress.json`.

## Hacia dónde va

VentaSys deja de ser un POS instalado para un negocio y pasa a ser un producto
que se vende por suscripción, con varias compañías sobre la misma base,
categorías de dos niveles, impuesto por producto tomado de CABYS y preparación
para factura electrónica.

El qué, el cómo y el trabajo pendiente están en [`.specify/`](.specify/).
