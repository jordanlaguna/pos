# VentaSys — Plan técnico

> **Qué es este documento.** Cómo se construye lo que define
> [spec.md](spec.md). Las tareas concretas y su orden están en
> [task.md](task.md).
>
> Actualizado: 2026-08-16

---

## 1. Arquitectura

### 1.1 Despliegue

Sin cambios de fondo. Lo que ya existe funciona y la razón por la que existe
sigue siendo válida.

```
Navegador ──HTTPS/LAN──> SvelteKit (BFF) ──HTTP interna──> FastAPI ──> MySQL 8
             cookie httpOnly            Bearer JWT
```

El navegador **nunca** habla con FastAPI: el JWT vive en una cookie httpOnly, no
hay CORS que configurar y la IP del backend no se expone. Toda pantalla nueva
—incluido el panel de soporte— entra por el mismo camino.

### 1.2 Capas (spec §5.5)

Hoy el backend está organizado por tipo de archivo —`models/`, `router/`,
`schemas/`, `services/`— que es una convención de framework, no una
arquitectura: `crud_sale.py` mezcla la regla de negocio, la consulta SQL y el
manejo de errores HTTP en la misma función. Por eso no hay forma de probar el
cálculo de una venta sin levantar MySQL.

**Destino:**

```
backend/app/
├── domain/                 puro. No importa nada de fuera.
│   ├── entities/           Sale, Product, CashSession, StockEntry
│   ├── values/             Money, TaxRate, Barcode, Consecutive
│   └── services/           reglas: totales, arqueo, validez de devolución
├── application/
│   ├── use_cases/          CreateSale, CloseCashSession, RegisterStockEntry
│   └── ports/              SaleRepository, ProductRepository, Clock,
│                           CabysCatalog, PasswordHasher, TokenIssuer
├── infrastructure/
│   ├── persistence/        modelos SQLAlchemy + repositorios (implementan puertos)
│   ├── security/           jwt_handler, bcrypt
│   └── external/           cliente CABYS
└── interfaces/http/        routers FastAPI + DTOs Pydantic
```

```
frontend/src/lib/
├── domain/                 money, totals, reglas del carrito. Sin Svelte, sin fetch
├── application/            casos de uso que invocan load y actions
├── infrastructure/         cliente HTTP, backend simulado, lectores de XML y planilla
└── ui/                     componentes y stores
frontend/src/routes/        transporte delgado
```

**Qué gana esto, en concreto:**

- El cálculo de totales con impuesto por línea (§6.3) se prueba con una tabla de
  casos, sin base de datos ni servidor.
- El filtro por compañía (§3.3) es cosa de `infrastructure/persistence/`: los
  casos de uso no se enteran, y no hay dónde olvidarse de aplicarlo.
- El puerto `Clock` vuelve estructural la regla de que la hora la pone el
  servidor. Con `datetime.now()` esparcido por los servicios, esa regla depende
  de que nadie se equivoque; con un puerto, un caso de uso que quiera saltársela
  no compila la prueba.
- La emisión de comprobantes (§7.2) es un puerto `EmisorFE` con dos
  implementaciones posibles. La decisión directo-o-proveedor deja de bloquear.

**Cómo se llega sin romper nada.** No de un tirón. El orden es:

1. **Pruebas de caracterización primero.** Antes de mover una línea, fijar el
   comportamiento actual con los invariantes ya verificados de `progress.json`
   (venta 3×1450, arqueo 53 277,00, devolución 1638,50, entrada XML 79 800…).
   Son la red: si después de mover el código siguen dando igual, el movimiento
   fue correcto.
2. **Extraer el dominio**, que es puro y no rompe nada al salir.
3. **Definir los puertos y mover los casos de uso**, dejando los `crud_*`
   actuales como adaptadores hasta que queden vacíos.
4. **Los routers adelgazan** a traducir HTTP y llamar al caso de uso.

Lo custodia el agente `architect`, con búsquedas que fallan si alguna capa
importa de más.

### 1.3 Pruebas (RNF-6)

Las capas y las pruebas son la misma decisión: el motivo de separar el dominio
es poder ejecutarlo solo.

| Dónde | Herramienta | Qué se prueba |
|---|---|---|
| `backend/app/domain`, `application` | **pytest** + `pytest-cov` | Cada función. Sin base, sin red, sin reloj real |
| `backend/app/infrastructure` | pytest contra MySQL en Docker | Cada adaptador y su caso de fallo |
| `frontend/src/lib/domain`, `application` | **Vitest** | Cada función |
| Flujos completos | **Playwright** | Cobrar, arquear, devolver, entrar mercadería |

**La cobertura rompe la build.** No es un informe que alguien mira: es un umbral.

```toml
# backend/pyproject.toml
[tool.coverage.report]
fail_under = 100
include = ["app/domain/*", "app/application/*"]
```

```ts
// frontend/vitest.config.ts
coverage: {
  include: ['src/lib/domain/**', 'src/lib/application/**'],
  thresholds: { lines: 100, functions: 100, branches: 100, statements: 100 }
}
```

Los umbrales cubren **solo** dominio y aplicación, a propósito. Exigir 100 % en
adaptadores e interfaz llevaría a escribir pruebas que confirman que SQLAlchemy
es SQLAlchemy: mucho trabajo y ninguna información. Ahí el criterio es cubrir el
camino real y el fallo, y los flujos se prueban de punta a punta.

**Las pruebas de caracterización son las primeras.** Los invariantes ya
verificados de `progress.json` —venta 3×1450 → 4 915,50; arqueo 53 277,00;
devolución 1 638,50; cierre contando 53 000 → −277,00; entrada XML 79 800—
dejan de comprobarse a mano y pasan a ser casos de prueba. Es la red para todo
lo que viene después.

Comandos: `cd backend && pytest`, `cd frontend && npm test`.

---

## 2. Reestructuración del repositorio (F0) — hecha el 2026-08-16

Se hizo **primero** y sin cambiar comportamiento, para que todo lo demás se
escriba una sola vez en su lugar definitivo.

```
antes                          después
─────────────────────────      ──────────────────────────────────────────
web/                     →     frontend/
backend-patch/           →     backend/          (ver la trampa de abajo)
backend/     (clon ref)  →     borrado
csharp-original/         →     borrado
docker/      (original)  →     borrado
deploy/                        en desuso; queda hasta migrar su volumen
                               .specify/         (este directorio)
```

**Los archivos de Docker quedaron en la raíz de `backend/`, no en un
subdirectorio.** Era la consecuencia de la decisión de abajo y no se había
previsto: si `backend/` es la aplicación completa, el Dockerfile ya tiene ahí al
lado el `app/`, el `requirements.txt` y el `wait-for-db.sh` que copia, así que
`docker compose up` corre desde `backend/` sin ensamblar nada. `deploy/` existía
únicamente porque el patch no era una aplicación; deja de tener razón de ser.

### La trampa del renombrado

`backend-patch/` **no es una aplicación**: son los 39 archivos que reemplazan o
agregan sobre el FastAPI original. La aplicación completa tiene 56. Renombrarlo
tal cual deja un backend que no arranca — faltarían, entre otros:

```
app/database/database.py        app/models/model_client.py
app/models/model_categories.py  app/models/model_person.py
app/models/model_sale_details.py app/schemas/schemas_product.py
app/services/crud_client.py     app/services/crud_categories.py   (+ 9 más)
```

**Decisión.** El nuevo `backend/` es la **aplicación completa**, tomada de
`deploy/app/` (que es el patch ya aplicado sobre el original) sin `.env` ni
`__pycache__`. Deja de ser un parche y pasa a ser el código fuente del backend,
que es lo que corresponde ahora que el original ya no es el ancestro sino el
punto de partida.

`backend/README.md` cambia de «cómo aplicar este patch» a «cómo correr este
backend», conservando la sección de los defectos corregidos: explica por qué el
código es como es.

### Qué se pierde al borrar

`backend/` (clon de `backend-python`) y `csharp-original/` son clones de
repositorios que siguen publicados en GitHub — las URL están en
`progress.json` → `proyecto.repos_origen`. Lo único irrecuperable sería el
análisis, y ese ya está escrito: los 10 defectos con su impacto viven en
`progress.json` → `defectos_corregidos` y en `backend/README.md`.

`docker/` es la carpeta original del usuario, cuyos seis problemas ya están
corregidos en el compose que sí se usa.

### Después de mover

Actualizar toda referencia a las rutas viejas: `CLAUDE.md`, `progress.json`,
`README.md`, los README internos, `.gitignore` y los cuatro agentes de
`.claude/agents/`. Se verifica con una búsqueda de `web/` y `backend-patch` en
todo el árbol; el criterio de terminado es que no quede ninguna viva —las
menciones históricas, las que cuentan cómo fue la migración, se conservan.

### El volumen no puede depender de la carpeta

Salió al verificar, y por poco cuesta la base de datos. Compose toma el nombre
del proyecto del **nombre del directorio** y lo usa de prefijo del volumen: el
stack levantado desde `deploy/` guarda los datos en `deploy_db_data`. Levantar
lo mismo desde `backend/` habría creado `backend_db_data`, vacío, y habría
parecido que se perdió todo.

Se corrigió fijando en el compose `name: ventasys` y el volumen
`ventasys_db_data`, que no dependen de dónde esté la carpeta. La migración del
volumen viejo queda pendiente (§8, F0).

---

## 3. Multiempresa (F2)

Es la fase que toca todo. Va primero: cualquier tabla que se cree después la
necesita, y hacerla al final significa migrar dos veces.

### 3.1 Tablas nuevas

```sql
CREATE TABLE companies (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    afiliado       INT          NOT NULL,
    compania       INT          NOT NULL,
    nombre         VARCHAR(160) NOT NULL,
    identificacion VARCHAR(30)  NULL,
    plan_id        INT          NOT NULL,
    estado         VARCHAR(20)  NOT NULL DEFAULT 'prueba',
    vence_el       DATE         NULL,
    creada_el      DATETIME     NOT NULL,
    -- La identidad del cliente es el par, no el id. El id existe para que las
    -- claves foráneas y los índices sean de 4 bytes y no de 8.
    UNIQUE KEY uq_companies_afiliado_compania (afiliado, compania),
    INDEX idx_companies_estado (estado)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE plans (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    nombre         VARCHAR(60)    NOT NULL,
    precio_mensual DECIMAL(10,2)  NOT NULL DEFAULT 0,
    max_sucursales INT            NOT NULL DEFAULT 1,
    max_terminales INT            NOT NULL DEFAULT 1,
    max_usuarios   INT            NOT NULL DEFAULT 3,
    factura_electronica TINYINT(1) NOT NULL DEFAULT 0
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE branches (          -- sucursales
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT          NOT NULL,
    codigo     CHAR(3)      NOT NULL,          -- 001, formato Hacienda
    nombre     VARCHAR(120) NOT NULL,
    activa     TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_branches (company_id, codigo),
    CONSTRAINT fk_branches_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE terminals (         -- cajas
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT          NOT NULL,
    branch_id  INT          NOT NULL,
    codigo     CHAR(5)      NOT NULL,          -- 00001, formato Hacienda
    nombre     VARCHAR(120) NOT NULL,
    activa     TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_terminals (company_id, branch_id, codigo),
    CONSTRAINT fk_terminals_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_terminals_branch  FOREIGN KEY (branch_id)  REFERENCES branches (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE audit_log (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT          NOT NULL,
    company_id INT          NULL,              -- sobre qué compañía se actuó
    accion     VARCHAR(60)  NOT NULL,
    detalle    VARCHAR(500) NULL,
    ip         VARCHAR(45)  NULL,
    creado_el  DATETIME     NOT NULL,
    INDEX idx_audit_company (company_id, creado_el)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
```

### 3.2 Tablas existentes

Todas reciben `company_id INT NOT NULL` con su índice, y **cada UNIQUE pasa a
ser compuesto**:

| Tabla | Cambio adicional |
|---|---|
| `users` | `company_id` NULL solo para el rol `soporte`. `email` sigue único global (RN-3). |
| `persons`, `clients` | `company_id`. |
| `categories` | `company_id`, `parent_id`, `orden`, `activa`. UNIQUE (company_id, parent_id, nombre). |
| `products` | `company_id`, `cabys_code`, `tax_rate`, `unidad_medida`, `activo`. UNIQUE (company_id, barcode). |
| `sales` | `company_id`, `branch_id`, `terminal_id`. UNIQUE (company_id, sale_number). |
| `sale_details` | `company_id` (redundante vía `sales`, pero necesario para el filtro automático). |
| `returns`, `return_details` | igual que ventas. |
| `cash_sessions`, `cash_movements` | `company_id`, `terminal_id`. |
| `stock_entries`, `stock_entry_details` | `company_id`, `branch_id`. |
| `settings` | Deja de ser una fila: `company_id` UNIQUE. |

`company_id` se repite en las tablas de detalle a propósito. Es
desnormalización, y se paga con un `INT` por fila a cambio de que el filtro
automático de la sección siguiente cubra **toda** consulta, incluidas las que
entran por el detalle sin pasar por la cabecera.

### 3.3 Cómo se garantiza el aislamiento

No con disciplina. Con tres capas:

**1. El `company_id` sale del token, nunca del cliente.** Se agrega al JWT al
iniciar sesión y `get_current_user` lo devuelve. Ningún endpoint lo acepta como
parámetro: si llega, se ignora.

**2. Filtro automático en SQLAlchemy.** Un `ContextVar` por petición y un
`with_loader_criteria` global:

```python
# app/utils/tenancy.py
current_company: ContextVar[int | None] = ContextVar("current_company", default=None)

class TenantMixin:
    """Lo heredan todos los modelos de negocio."""
    company_id = Column(Integer, nullable=False, index=True)

@event.listens_for(Session, "do_orm_execute")
def _filtrar_por_compania(state):
    if state.is_select and not state.execution_options.get("sin_filtro_de_compania"):
        cid = current_company.get()
        if cid is not None:
            state.statement = state.statement.options(
                with_loader_criteria(TenantMixin, lambda cls: cls.company_id == cid,
                                     include_aliases=True)
            )
```

Olvidar el `WHERE` deja de ser posible en las consultas del ORM. Para las pocas
que necesitan cruzar compañías —el panel de soporte— hay que pedirlo explícito
con `sin_filtro_de_compania`, que es justo lo que se quiere: que salte a la
vista al leer el código.

**Límite conocido:** `with_loader_criteria` cubre SELECT del ORM. **No** cubre
el SQL agregado de `crud_report.py` ni los `UPDATE`/`DELETE` masivos. Esos
llevan el filtro escrito a mano y una prueba que lo verifica. Está anotado como
riesgo en §9.

**3. Pruebas que intentan cruzarse.** Dos compañías sembradas y una batería que
recorre **todos** los endpoints pidiendo, con el token de la compañía A, los
identificadores de la B. Toda respuesta debe ser 404 (no 403: un 403 confirma
que el recurso existe). Sin esta prueba la fase no está terminada.

### 3.4 Migración de lo que ya hay

```sql
INSERT INTO plans (id, nombre, precio_mensual, max_sucursales, max_terminales, max_usuarios)
     VALUES (1, 'Comercio', 25000, 1, 3, 10);

INSERT INTO companies (id, afiliado, compania, nombre, plan_id, estado, creada_el)
     VALUES (1, 1, 1, 'Compañía inicial', 1, 'activa', NOW());

-- Toda fila existente pasa a la compañía 1.
UPDATE products SET company_id = 1;   -- ídem para cada tabla
```

El sistema actual queda como afiliado 1, compañía 1, activa, sin perder nada.
Los `ALTER TABLE ... ADD COLUMN company_id NOT NULL DEFAULT 1` se ejecutan con
el valor por omisión y **después** se le quita el DEFAULT, para que las filas
nuevas estén obligadas a decir a quién pertenecen.

---

## 4. Panel de soporte (F3)

Grupo de rutas `/admin` en el mismo despliegue, no una aplicación aparte:
duplicar autenticación y despliegue para cinco pantallas no se paga.

- Solo rol `soporte`, verificado en el servidor en cada `load` y cada acción.
- Su sesión **no tiene compañía**: las pantallas del POS le responden 403.
- *Entrar como* emite un token con el `company_id` de la compañía destino, con
  vencimiento corto y motivo obligatorio, y escribe en `audit_log`. La interfaz
  muestra una franja permanente mientras dure.
- Toda acción de soporte se registra: alta, cambio de estado, entrada.

---

## 5. Categorías de dos niveles (F4)

`parent_id` con `NULL` para las raíces. Aunque el árbol quede limitado a dos
niveles por regla (RN-5), la columna permite abrir un tercero sin migrar.

La profundidad se valida en el servicio, no en la base: al crear una categoría
con `parent_id`, se verifica que el padre sea raíz. Un `CHECK` de MySQL no
alcanza para esto.

Migración: las categorías actuales quedan como raíces sin hijas. Nada se rompe.

---

## 6. Impuesto por producto y CABYS (F5)

### 6.1 Contrato del API — verificado el 2026-08-16

```
GET https://api.hacienda.go.cr/fe/cabys?q=<texto>&top=<n>
→ { "total": 16, "cantidad": 3,
    "cabys": [ { "codigo": "2312000000300",
                 "descripcion": "Harina de arroz",
                 "categorias": [ …8 niveles… ],
                 "impuesto": 13,
                 "uri": "…?codigo=2312000000300",
                 "estado": "" } ] }

GET https://api.hacienda.go.cr/fe/cabys?codigo=<13 dígitos>
→ [ { "categorias": […], "codigo": "…", "descripcion": "…", "impuesto": 13 } ]
```

**Ojo:** la consulta por texto devuelve un **objeto** con la lista adentro; la
consulta por código devuelve una **lista pelada**. Formas distintas en el mismo
endpoint; el lector tiene que contemplar las dos.

Tarifas comprobadas: harina de arroz 13 %, medicamentos 2 %, libros infantiles
0 %. La tarifa viene en el catálogo, que es exactamente el motivo por el que el
impuesto no puede ser un número global.

También existe `GET /fe/ae?identificacion=<cédula>` para la actividad económica;
responde 404 con un mensaje en inglés cuando la cédula no existe.

### 6.2 Diseño

- **Proxy en FastAPI**, no llamada desde el navegador: el POS puede estar en una
  LAN sin salida, no queremos exponer internet al cliente ni pelear con CORS, y
  así la respuesta se puede cachear una vez para todas las compañías.
- **Tabla `cabys_cache`** (`codigo` PK, `descripcion`, `impuesto`,
  `actualizado_el`), global y no por compañía: el catálogo es el mismo para
  todos. Se llena con los códigos que se van usando.
- Al asignar un código a un producto se copia la tarifa y se guarda en caché,
  de modo que **facturar no depende de que Hacienda esté arriba**.
- Sin internet, la búsqueda responde desde la caché y lo dice.

### 6.3 Impuesto por línea

`computeTotals` deja de recibir una tasa y pasa a recibir líneas con su propia
tarifa:

```ts
computeTotals([{ price, quantity, taxRate }, …])
  → { subtotal, tax, total, porTarifa: [{ tarifa, base, impuesto }] }
```

El desglose `porTarifa` es lo que necesitan el documento impreso (RF-21) y, más
adelante, el XML de Hacienda. Toca `money.ts`, el carrito, `crud_sale`,
`crud_return`, los reportes, las tres plantillas y el mock. Es la parte más
invasiva de la fase y conviene hacerla de un solo tirón.

---

## 7. Facturación electrónica

### 7.1 Certificado y PIN (entra en F6)

```sql
CREATE TABLE fe_credentials (
    company_id     INT PRIMARY KEY,
    archivo        LONGTEXT     NOT NULL,   -- .p12 cifrado, base64
    pin            VARBINARY(512) NOT NULL, -- cifrado
    nombre_archivo VARCHAR(160) NULL,
    vence_el       DATE         NULL,
    subido_el      DATETIME     NOT NULL,
    subido_por     INT          NOT NULL,
    CONSTRAINT fk_fe_credentials_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
```

- **AES-256-GCM** con llave de 32 bytes en la variable de entorno
  `FE_CRYPTO_KEY`, con el `company_id` como dato asociado: un registro copiado a
  otra compañía no descifra.
- La llave vive **fuera de la base**. Un respaldo robado no alcanza para firmar.
- El `.p12` se descifra en memoria, solo al firmar, y no se escribe a disco.
- `GET` devuelve `{ configurado, nombre_archivo, vence_el, subido_el }`. El
  archivo y el PIN **no tienen** endpoint de lectura. No existe el camino.
- No se registran en bitácora ni en trazas de error.

**Consecuencia asumida:** si se pierde `FE_CRYPTO_KEY`, cada compañía tiene que
volver a subir su certificado. Es preferible a la alternativa, que es que la
llave viaje con los datos que protege.

### 7.2 Emisión (F7 — decisión pendiente)

No se programa hasta decidir la ruta. Lo que hay que resolver:

| | Directo | Vía proveedor autorizado |
|---|---|---|
| Firma XAdES-EPES | nuestra | del proveedor |
| Cambios de esquema de Hacienda | los seguimos nosotros | los sigue el proveedor |
| Costo | cero por documento | mensual o por documento |
| Salir a producción | lento | rápido |
| Dependencia | ninguna | fuerte |

**Diseño que no obliga a decidir hoy:** la emisión se define como una interfaz
(`EmisorFE`: `emitir(venta) → {clave, consecutivo, estado}`, `consultar(clave)`)
con dos implementaciones posibles. Todo lo demás —CABYS, tarifas, numeración,
sucursal, terminal, datos del receptor, cola de reintentos, contingencia— es
igual en ambos casos y es lo que se construye en F5 y F6.

Piezas que faltarían en cualquiera de las dos rutas: clave de 50 dígitos,
consecutivo de 20 sin huecos (con bloqueo de fila por terminal), envío
asíncrono con consulta de estado, entrega al receptor por correo con XML y PDF,
y modo contingencia para poder cobrar con Hacienda caída.

---

## 8. Fases

| Fase | Qué deja | Terminado cuando |
|---|---|---|
| **F0** Repositorio ✅ | `frontend/`, `backend/`, sin clones de referencia | El sistema levanta igual y no queda ninguna referencia a las rutas viejas |
| **F1** Arquitectura y pruebas | Capas, puertos, y la infraestructura de pruebas con cobertura exigida | El dominio no importa nada, los invariantes de `progress.json` siguen dando igual y la build se cae si baja la cobertura |
| **F2** Multiempresa | `company_id` en todo, filtro automático, migración | Las pruebas de cruce entre compañías dan 404 en todos los endpoints |
| **F3** Soporte | Panel `/admin`, planes, estados, bitácora | Se puede dar de alta una compañía y operarla de punta a punta |
| **F4** Categorías | Dos niveles en catálogo, ventas e inventario | Un repuestero y un súper organizan su catálogo sin tocar código |
| **F5** Impuesto y CABYS | Tarifa por producto, búsqueda de CABYS, totales por línea | Una venta con 13 %, 2 % y 0 % cuadra y desglosa bien |
| **F6** Preparación FE | Certificado cifrado, sucursales, terminales, actividad | Se sube un `.p12`, se ve su estado y no hay forma de leerlo de vuelta |
| **F7** Emisión | (decisión pendiente) | — |

**F1 va primero y no es opcional.** Todo lo que sigue toca dinero, existencias o
aislamiento entre compañías, y sin pruebas que fijen el comportamiento actual no
hay forma de saber si un cambio rompió algo: los invariantes de `progress.json`
se verifican hoy a mano, una vez, y eso no escala a seis fases más. Además, F2
mete un filtro por compañía en la capa de persistencia, que es justamente la
capa que F1 crea.

F4 y F5 pueden ir en paralelo. F6 depende de F2.

---

## 9. Riesgos

| Riesgo | Mitigación |
|---|---|
| Una consulta sin filtro filtra datos entre compañías | Filtro automático en el ORM + pruebas de cruce en todos los endpoints |
| `with_loader_criteria` no cubre el SQL agregado de reportes ni los UPDATE masivos | Filtro escrito a mano en `crud_report.py`, con prueba propia. Revisar en cada agregado nuevo |
| El refactor de F2 toca todos los archivos y puede romper lo que ya funciona | Las pruebas de F1 son la red. Por eso F1 va antes: los invariantes de `progress.json` dejan de comprobarse a mano y pasan a correr solos |
| Reorganizar por capas (F1) es mover mucho código sin cambiar comportamiento, que es donde se cuelan los errores silenciosos | Pruebas de caracterización **antes** de mover nada, y se mueve capa por capa, no todo junto |
| La cobertura del 100 % empuja a escribir pruebas de relleno para pasar el umbral | El umbral cubre solo dominio y aplicación, que son código puro y de reglas. Ahí una función sin prueba es una regla sin verificar, no burocracia |
| `FE_CRYPTO_KEY` se pierde | Documentado: hay que volver a subir los certificados. Se guarda fuera del repositorio y fuera de la base |
| El API de CABYS no responde | Caché local; la venta nunca depende de él |
| Borrar los clones de referencia | Están en GitHub y el análisis quedó escrito en `progress.json` y en `backend/README.md` |
| El impuesto por línea toca dinero ya verificado | Los invariantes de `progress.json` se recalculan y se documentan de nuevo |
