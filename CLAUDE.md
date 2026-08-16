# VentaSys — contexto para Claude Code

Punto de venta migrado de C#/WinForms a SvelteKit, sobre FastAPI + MySQL en
Docker. Idioma de la interfaz: español de Costa Rica, con voseo. Moneda: colones.
IVA 13 %.

## Al empezar una sesión

**Leé `.specify/`.** Son cuatro documentos y cada hecho vive en uno solo:

| Archivo | Qué guarda |
|---|---|
| `spec.md` | Qué se construye y por qué. Requisitos numerados (RF, RN, RNF). |
| `plan.md` | Cómo. Arquitectura, modelo de datos, fases, riesgos del plan. |
| `task.md` | El trabajo pendiente, en orden y con su verificación. |
| `progress.json` | Lo que ya pasó: decisiones con su porqué, defectos corregidos, cifras de referencia y bitácora. |

Los tres primeros miran hacia adelante; `progress.json` mira hacia atrás. Ahí
está el giro grande del proyecto: VentaSys pasa de ser un POS para un negocio a
un producto multiempresa que se vende por suscripción.

Si dos se contradicen sobre qué falta, manda `task.md`.

## Al terminar una sesión

**Actualizá `.specify/progress.json`** si hubo cambios que importen:

- `actualizado` con la fecha de hoy.
- Una entrada nueva en `sesiones` con lo que se hizo.
- `decisiones` si se decidió algo con consecuencias.
- `defectos_corregidos` si se arregló un defecto real.
- `invariantes_verificados` si cambia alguna cifra de referencia.

Y **marcá en `.specify/task.md`** lo que quedó terminado, agregando lo que haya
aparecido. Los pendientes viven ahí, no en `progress.json`.

Es un registro de trabajo, no un diario: anotá lo que le sirva a quien retome,
no cada archivo que se tocó.

## Mapa

```
.specify/            spec.md, plan.md, task.md, progress.json
frontend/            el POS (SvelteKit 2, Svelte 5 runes, Tailwind 4)
backend/             la API (FastAPI + MySQL). Se levanta sola con su compose.
docs/                ejemplos de factura y material de Hacienda (XSD 4.4)
deploy/              despliegue viejo, en desuso. NO se versiona.
```

`backend/` es la aplicación completa, no un parche: se levanta con
`docker compose up` desde su propia carpeta. `deploy/` existía solo porque antes
había que ensamblar el backend a partir de un patch; ya no hace falta y se puede
borrar en cuanto se migre su `.env` y su volumen de datos.

## Levantar

```bash
cd backend && docker compose up -d --build    # backend + MySQL en :8001
cd backend && python seed.py --ventas 35      # datos de prueba
cd frontend && npm run dev                    # POS en :5173
```

Para desarrollar sin backend: `POS_MOCK=1` en `frontend/.env`.

## Reglas del proyecto

- **El dinero se calcula en el servidor**, releyendo los precios del backend.
  Toda aritmética monetaria pasa por `$lib/money.ts`, que redondea a 2 decimales
  en cada paso.
- **La moneda y el impuesto se configuran**, no se escriben en el código. Salen
  de `/configuracion` (tabla `settings`) vía `$lib/settings.ts`. En un `load` o
  una acción hay que leerlos con `loadSettings()` y pasar la tasa explícita a
  `computeTotals`: el estado de módulo de `money.ts` lo fija el layout al
  renderizar, y ahí todavía no corrió.
- **Una devolución usa la tasa de SU venta** (`tax / subtotal`), no la
  configurada hoy. Si el dueño cambia el IVA, lo que se reembolsa sigue siendo
  lo que se cobró.
- **La hora de las ventas la pone el backend**, nunca el cliente. El arqueo de
  caja depende de comparar marcas del mismo reloj.
- **Los permisos se aplican en el servidor** (`requireUser`, `requireAdmin` en
  cada `load` y cada `action`). Esconder un botón no es control de acceso.
- **El modo mock se mantiene sincronizado.** Un endpoint nuevo en FastAPI va
  también a `frontend/src/lib/server/mock/handler.ts`, con contrato idéntico.
- **Los colores salen de los tokens de `app.css`.** Hay tema claro y oscuro. El
  acento se puede cambiar desde Configuración: el tono oscuro y el color del
  texto se derivan en OKLab (`$lib/color.ts`), nunca se eligen a ojo.
- **Arquitectura limpia.** Las dependencias apuntan hacia adentro: `domain` no
  importa nada, `application` habla con puertos, `infrastructure` e `interfaces`
  son los adaptadores. Si para probar una regla hay que levantar la base, la
  regla está en la capa equivocada. Lo custodia el agente `architect`; el
  destino está en `.specify/plan.md` §1.2.
- **Cada función tiene su prueba.** En `domain/` y `application/` es
  obligatorio y la cobertura rompe la build (100 %). En adaptadores, prueba de
  integración; en la interfaz, flujos de punta a punta. Una función nueva de
  esas dos capas sin prueba está incompleta, no «pendiente».
- **El código va en inglés** —identificadores, archivos, tablas, columnas,
  rutas—, igual que el código heredado (`products`, `sales`, `company_id`).
  **La interfaz va en español de Costa Rica** y **la documentación también**.
- Al terminar: `cd frontend && npm run check` en 0 errores y 0 advertencias,
  `npm test` y `cd backend && pytest` en verde.

## Git

- **El autor de los commits es el usuario, nunca Claude.** Sin línea
  `Co-Authored-By`, sin mención en el cuerpo, sin `--author`. Es su repositorio y
  su autoría; el trailer haría que GitHub muestre a Claude como coautor en todo
  el historial.
- **Identidad por repositorio, no global.** Acá va la cuenta personal
  (`jordanlaguna` / `jordanlaguna10@gmail.com`); la global de la máquina es la
  del trabajo y no se toca.
- El remoto lleva el usuario en la URL
  (`https://jordanlaguna@github.com/…`). Sin eso, git reutiliza el token del
  trabajo en silencio y GitHub responde `404 Repository not found` —no `403`—
  cuando el repositorio personal no le es visible.

## Trampas conocidas

- El puerto de la API es **8001**, no 8000 (el compose publica `"8001:80"`).
- `node build/index.js` **no lee el `.env`**: hace falta `--env-file=.env`.
- `ORIGIN` es obligatoria en producción o todo POST responde 403.
- Con `curl` contra el POS hay que mandar `-H "Origin: http://localhost:3000"`.

## Agentes del proyecto

| Agente | Para qué |
|---|---|
| `pos-fullstack` | Implementar funcionalidad que cruza frontend y backend. |
| `pos-qa` | Verificar de punta a punta contra el stack real. |
| `pos-deploy` | Docker, variables de entorno, red, respaldos, diagnóstico. |
| `pos-auditor` | Revisar plata, stock, caja y permisos. Solo lee. |
| `architect` | Custodia las capas: dependencias hacia adentro, puertos, y que dominio y aplicación tengan prueba. Solo lee. |
| `spec-reviewer` | Revisa `.specify/spec.md`: verificable, sin CÓMO, sin contradicciones. Solo lee. |
| `plan-reviewer` | Revisa `.specify/plan.md` contra el spec y el código. Solo lee. |
| `task-reviewer` | Revisa `.specify/task.md`: nada sin tarea, nada sin verificación, y que lo marcado sea cierto. Solo lee. |

Los cuatro últimos revisan, no escriben. Conviene pasarles el documento antes de
empezar una fase y al cerrarla.
