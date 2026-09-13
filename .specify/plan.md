# VentaSys — Plan técnico

> **Qué es este documento.** Cómo se construye lo que define
> [spec.md](spec.md). Las tareas concretas y su orden están en
> [task.md](task.md).
>
> Actualizado: 2026-09-11

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
│   ├── entities/           Sale, Product, CashSession, StockEntry,
│   │                       Supplier, JournalEntry, Employee, PayrollRun (F10–F12)
│   ├── values/             Money, TaxRate, Barcode, Consecutive, RateSet
│   └── services/           reglas: totales, arqueo, validez de devolución,
│                           promedio ponderado, asiento por evento, planilla
├── application/
│   ├── use_cases/          CreateSale, CloseCashSession, RegisterStockEntry,
│                           RegisterPurchase, ClosePeriod, PayRun
│   └── ports/              SaleRepository, ProductRepository, Clock,
│                           CabysCatalog, PasswordHasher, TokenIssuer,
│                           Ledger, RateTable
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

-- Membresía: qué persona entra a qué compañía y con qué rol.
--
-- Existe porque `users` es la IDENTIDAD (un correo, una contraseña) y la
-- pertenencia es otra cosa. Repetir el correo con UNIQUE (company_id, email)
-- parecía más simple, pero crea tres cuentas distintas que solo se parecen en
-- el texto del correo: tres contraseñas que se desincronizan, y un login que
-- tendría que preguntar la compañía ANTES de autenticar —o sea, mostrarle la
-- cartera de clientes a cualquiera que escriba un correo (RN-24).
CREATE TABLE user_companies (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT         NOT NULL,
    company_id INT         NOT NULL,
    rol        VARCHAR(20) NOT NULL,          -- por compañía, no por persona
    activa     TINYINT(1)  NOT NULL DEFAULT 1,
    creada_el  DATETIME    NOT NULL,
    UNIQUE KEY uq_user_companies (user_id, company_id),
    INDEX idx_user_companies_company (company_id),
    CONSTRAINT fk_uc_user    FOREIGN KEY (user_id)    REFERENCES users (id_user),
    CONSTRAINT fk_uc_company FOREIGN KEY (company_id) REFERENCES companies (id)
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

**Doce** tablas reciben `company_id INT NOT NULL` con su índice y su clave
foránea, y **cada UNIQUE pasa a ser compuesto**:

| Tabla | Cambio adicional |
|---|---|
| `users` | **No lleva `company_id` ni `role`.** Queda como identidad: `email` único global y una contraseña. La pertenencia y el rol pasan a `user_companies` (RN-3). Soporte es una persona sin ninguna membresía. |
| `persons` | **Tampoco lleva `company_id`.** Ver la corrección de abajo. |
| `clients` | `company_id`. UNIQUE (company_id, identification) y (company_id, email). |
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

**Corrección al escribir la migración: `persons` es identidad, no negocio.**

Esta sección decía «`persons`, `clients` → `company_id`», y al ir a escribirlo se
vio que `persons` es 1 a 1 con `users`: `/persons/register` crea las dos filas
juntas y ninguna otra tabla la referencia. O sea que `persons` no guarda datos de
clientes —esos están en `clients`— sino el nombre y la cédula de la misma
identidad que representa `users`.

Ponerle `company_id` obligaría a decidir a qué compañía «pertenece» el contador
que atiende tres locales, que es exactamente el problema que T-216 acababa de
resolver para `users`. Queda global, con su cédula única en todo el sistema: dos
personas distintas no comparten cédula aunque trabajen en compañías distintas.

Por eso la cuenta da doce y no catorce. Lo que sí cambió es quién puede verlas:
`/persons/persons_list` devolvía la libreta entera de la base y ahora se une con
`user_companies` para devolver solo las de la compañía de la sesión.

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

class SinCompania(Exception):
    """Se intentó leer una tabla de negocio sin compañía en la petición."""

@event.listens_for(Session, "do_orm_execute")
def _filtrar_por_compania(state):
    if not state.is_select:
        return
    if state.execution_options.get("sin_filtro_de_compania"):
        return                       # única salida, y se pide por escrito
    cid = current_company.get()
    if cid is None:
        # Falla cerrado. Ver más abajo: la versión que dejaba pasar era un
        # agujero, no una comodidad.
        raise SinCompania(state.statement)
    state.statement = state.statement.options(
        with_loader_criteria(TenantMixin, lambda cls: cls.company_id == cid,
                             include_aliases=True)
    )
```

Olvidar el `WHERE` deja de ser posible en las consultas del ORM. Para las pocas
que necesitan cruzar compañías —el panel de soporte— hay que pedirlo explícito
con `sin_filtro_de_compania`, que es justo lo que se quiere: que salte a la
vista al leer el código.

**Por qué falla cerrado.** La primera versión de este filtro decía `if cid is
not None: aplicar`. Con un usuario por compañía nunca se notaba, porque el
`company_id` siempre venía en el token. La pantalla de selección (RF-27) crea
justo el estado que faltaba: **autenticado y todavía sin compañía**. Con la
versión permisiva, una consulta en esa ventana no se filtra por nada y devuelve
las filas de **todas** las compañías —sin error, sin aviso, en un reporte que se
ve perfecto—. Lo mismo pasaba con soporte, que tiene la compañía en nulo: veía
todo por omisión, no por haberlo pedido, que es lo contrario de lo que dice el
párrafo anterior.

Ahora la ausencia de compañía es una excepción. El panel de soporte y el propio
login —que consulta `users` y `user_companies` antes de que haya compañía— pasan
por `sin_filtro_de_compania`, escrito y visible.

**Ajuste al implementarlo: se exige compañía solo si la consulta toca negocio.**

El esbozo de arriba lanza `SinCompania` en toda consulta sin compañía. Escrito
así, el login —que lee `users` y `user_companies` antes de que exista compañía—
tendría que marcarse con `sin_filtro_de_compania`, igual que cualquier lectura de
identidad. Y ahí la marca deja de significar algo: si aparece en las consultas
normales, ya no señala «acá se cruzan compañías a propósito», que es lo único que
la hace útil al leer el código.

La versión implementada mira `state.all_mappers` y solo exige compañía si la
consulta involucra alguna clase que herede `TenantMixin`. No se pierde nada:
una consulta que no toca ninguna tabla de negocio no puede filtrar datos de
negocio.

**La otra mitad: sellar la escritura.**

El plan solo cubría la lectura, y eso deja el aislamiento cojo. Si leer sin
`WHERE company_id` es imposible pero escribir sin `company_id` depende de que
quince sitios se acuerden, el fallo entra por el lado de la escritura: una venta
guardada sin compañía queda visible para nadie —o, peor, para quien tenga ese
número— y el defecto aparece semanas después, cuando ya hay datos encima.

Se resuelve con el mismo mecanismo y en el mismo archivo:

```python
@event.listens_for(Session, "before_flush")
def _sellar_compania(session, flush_context, instances):
    for objeto in session.new:
        if isinstance(objeto, TenantMixin) and objeto.company_id is None:
            objeto.company_id = compania_actual()   # falla cerrado
```

No pisa lo que ya venga puesto: `bootstrap.py` y las semillas crean filas de una
compañía distinta de la del contexto a propósito.

Sucursal y terminal se sellan igual pero **explícitas**, en los cuatro
repositorios que registran hechos (`sucursal_actual()`, `terminal_actual()`).
Ahí la magia no ayudaría: `Terminal.branch_id` también se llama así y significa
otra cosa.

**Límite conocido, y es más ancho de lo que parecía.** `with_loader_criteria`
cubre los SELECT del ORM que **cargan entidades**. No cubre:

- el SQL agregado de `crud_report.py` ni los `UPDATE`/`DELETE` masivos —eso ya
  estaba previsto, y esos llevan su `company_id ==` escrito a mano, siete
  consultas, con prueba propia—;
- **`Query.count()`**, que no estaba previsto. `count()` no ejecuta la consulta
  de la entidad: la envuelve en `SELECT count(*) FROM (…)` y el criterio no
  entra en la envoltura. O sea que `db.query(Product).all()` devuelve solo las
  propias pero `db.query(Product).count()` cuenta las de **todas**.

Lo segundo es más peligroso que lo primero, porque un `.count()` no parece SQL
agregado: parece una llamada inocente del ORM. Se descubrió al escribir la
prueba de T-206 —no había ninguna fuga en el código, pero el hueco estaba— y la
respuesta fue un guardián: `tests/test_tenancy.py` recorre el árbol de sintaxis
de `app/` y tumba `pytest` si aparece un `.count()` sin `company_id` ni
`sin_filtro` en la misma sentencia. La forma que sí se filtra es
`db.query(func.count(Modelo.id))`, porque ahí la columna pertenece a la entidad.

Está anotado como riesgo en §10.

**Dónde se fija la compañía, y por qué la dependencia es asíncrona.**

FastAPI corre las dependencias síncronas en un hilo aparte, con una **copia** del
contexto: un `ContextVar` fijado ahí no se ve desde el endpoint. Las asíncronas
corren en la misma tarea que la petición. Por eso `payload_del_token` es `async`
y no lo es por gusto; si alguien la vuelve síncrona, el filtro deja de recibir la
compañía y todo empieza a lanzar `SinCompania`.

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

Cada usuario actual recibe su membresía con el rol que ya tenía, antes de que
`users.role` desaparezca:

```sql
INSERT INTO user_companies (user_id, company_id, rol, activa, creada_el)
     SELECT id_user, 1, role, 1, NOW() FROM users;
```

### 3.5 Entrar: dos pasos, no uno

Con membresías, el login deja de ser una sola operación. Se parte en dos, con un
estado intermedio corto y sin permisos (RN-26).

```
correo + contraseña ─┬─► 1 compañía disponible ──► adentro          (RN-25)
                     └─► 2 o más ──► elegir compañía ──► adentro    (RF-27)
```

**Paso 1 — autenticar.** `POST /auth/login` valida la contraseña y devuelve un
token **de tránsito**: lleva `sub` (la persona) y *no* lleva `cid`. Dura pocos
minutos y solo sirve para dos endpoints: listar las compañías propias y elegir
una. Cualquier ruta de negocio lo rechaza con 401 —y aunque no lo hiciera, el
filtro de §3.3 falla cerrado.

**Paso 2 — elegir.** `POST /auth/company` recibe el `company_id`, verifica que
exista la membresía **activa** y que el estado de la suscripción deje entrar, y
devuelve el token de sesión, ahora sí con `cid` y con el `rol` de esa membresía.
Queda en bitácora.

Reglas que no son cosméticas:

- **La lista solo se ve con un token**, de tránsito o de sesión (RN-24). Si se
  pudiera pedir con el correo a secas, cualquiera enumeraría los clientes del
  producto escribiendo direcciones. Que también valga el token de sesión es lo
  que permite cambiar de compañía sin volver a escribir la contraseña (RF-28):
  prueba la identidad igual de bien, y lo único que deja ver son las membresías
  propias.
- **Una sola compañía disponible ⇒ no hay pantalla** (RN-25). El backend
  devuelve el token de sesión directo en el paso 1, y el cajero no se entera de
  que esto existe.
- **Las bloqueadas se listan igual, con su motivo** (RF-27). Una compañía
  suspendida que simplemente no aparece se lee como «me borraron la cuenta».
- **Cambiar de compañía re-emite el token** y limpia el estado del navegador
  (RN-27): carrito, ventas en espera y la caché de configuración de §3.6.

### 3.6 La caché de configuración es de una sola compañía

`frontend/src/lib/server/settings.ts` guarda la configuración en una variable de
módulo:

```ts
let cache: { value: StoredSettings; at: number } | null = null;
```

Esa variable vive en el proceso de Node, no en la petición. Con una compañía es
correcto y ahorra una llamada por pantalla. Con varias, **la primera compañía
que cargue una página le presta su nombre, su logo, su moneda y su color de
acento a todas las demás durante 30 segundos**. `invalidateSettings()` tiene el
mismo problema al revés: quien guarda le borra la caché a todos.

La caché pasa a estar indexada por compañía (`Map<company_id, …>`) y la
invalidación a ser de una sola. Entra en F2 junto con el resto del aislamiento,
no después: es exactamente el mismo defecto que el `WHERE` olvidado, solo que en
el otro lado del BFF.

### 3.7 Respaldar y restaurar una sola compañía (T-217, herramienta en T-225)

Con base compartida, devolverle sus datos a un cliente deja de ser un
`mysqldump`. La decisión, tomada al escribir la migración:

**Se restaura solo lo que no está.** `auto_increment` de MySQL nunca reutiliza un
número, así que las filas de una compañía dada de baja dejan sus identificadores
libres para siempre. La restauración los conserva tal cual y no remapea nada
—remapear claves entre doce tablas es donde este tipo de herramienta se rompe—.
El precio es que restaurar sobre una compañía que todavía tiene filas está
prohibido: el guion se niega antes de tocar nada, en vez de mezclar.

**El orden lo dictan las claves foráneas**, no el guion. Por eso la migración las
crea: al exportar e importar, la base misma obliga a hacerlo bien y un error de
orden falla en vez de dejar huérfanos.

**`users` se exporta por correo, no por fila.** Es identidad global y puede estar
compartida con otra compañía que sigue viva; copiar la fila crearía una cuenta
duplicada o chocaría con el UNIQUE. Se exportan las membresías y, al restaurar,
se busca la cuenta por correo y se crea solo si no existe.

**Sirve para dos cosas distintas** y por eso vale la pena hacerlo bien: devolver
los datos a quien se da de baja, y volver atrás cuando una compañía se daña sin
tocar a las otras once que están vendiendo en ese momento.

Implementado en `backend/company_dump.py` (`exportar`, `borrar`, `importar`).
Borrar pide el par afiliado-compañía escrito a mano: es la única operación que
destruye datos, y un `--compania 2` mal tecleado se lleva el negocio equivocado
sin ninguna otra señal. Una prueba —`verificar_cobertura()`— falla si aparece una
tabla que nadie clasificó, porque una exportación incompleta se descubre el día
que hace falta restaurar, que es el peor día para descubrirlo.

### 3.8 La membresía se acepta, no se impone (T-229)

Un administrador tiene que poder sumar a su compañía a alguien que ya tiene
cuenta: es la única forma de armar el caso del contador que atiende tres locales
(RN-3). Pero poder sumarlo no es poder entrar por él.

La primera versión daba el acceso de una: el administrador escribía un correo y
esa compañía aparecía en la lista de la otra persona al entrar. No le hacía daño
—tenía que elegirla para que pasara algo— pero tampoco le había preguntado. Con
base compartida eso pesa más de lo que parece: la lista de compañías de alguien
dice con quién trabaja, y llenársela de invitados ajenos es ruido y, peor, una
superficie de engaño —basta dar de alta una compañía con nombre parecido al suyo
para que aparezca ahí, al lado de la de verdad—.

`user_companies.aceptada_el` en nulo significa «invitada, sin responder». Los
tres estados de una fila:

| `activa` | `aceptada_el` | Qué es |
|---|---|---|
| 1 | nulo | invitación pendiente: se ve, no abre |
| 1 | fecha | membresía en uso |
| 0 | — | revocada por el administrador, o rechazada por la persona |

La frontera está en **quién crea la cuenta**:

- `POST /users/` la crea el administrador, con el correo y la contraseña que él
  eligió. Nace **aceptada**: pedirle a esa cuenta que acepte una invitación a sí
  misma no protegería a nadie.
- `POST /users/membership` suma una identidad **que ya existía**. Nace
  **pendiente**.
- `bootstrap.py` nace aceptada, por lo mismo que el primer caso y porque una
  invitación que nadie puede aceptar dejaría la instalación sin poder entrar.

Reinvitar a quien rechazó vuelve a dejar la membresía pendiente: haber dicho que
no una vez no es haber dicho que sí.

### 3.9 Las columnas de la suscripción se quedan en español (T-913, decidido el 2026-09-05)

`companies`, `plans`, `user_companies`, `branches` y `terminals` tienen sus
columnas en **español** —`afiliado`, `compania`, `nombre`, `identificacion`,
`estado`, `vence_el`, `creada_el`, `precio_mensual`, `max_sucursales`,
`max_terminales`, `max_usuarios`, `factura_electronica`, `rol`, `activa`,
`aceptada_el`, `codigo`—, contra la regla de código en inglés. Vienen de la
migración 002 y son la única excepción: F4 no las siguió y usó `sort_order` e
`is_active`.

**Se aceptan como están.** No es pereza; es que el rename no es un rename:

- Son **58 archivos y unas 890 menciones**, medidas, no estimadas.
- **Trece de los diecisiete nombres son claves JSON publicadas** —`CompanyOption`,
  `CompanyOut`, `PlanOut`, `NewCompany`, `SubscriptionUpdate`— y hay que moverlas
  en el mismo commit en cinco frentes que **no comparten compilador**: modelo y
  migración, esquemas Pydantic, el simulado, los tipos y formularios de `/admin`,
  y los catálogos `es`/`en`/`pt`. `npm run check` no ve el backend y `pytest` no
  ve el POS, así que una clave que quede vieja **no rompe la build**: devuelve
  `undefined` en pantalla.
- El punto de no retorno es `company_dump.py`. Exporta **por nombre de columna**
  (`fila._mapping`) y su `FORMATO = 1` no cambia con un rename, así que la guarda
  de versión deja pasar un respaldo viejo como si fuera compatible y revienta
  después, al insertar. **Todo respaldo entregado a un cliente antes del cambio
  quedaría inservible**, en silencio, hasta el día que haya que restaurarlo —que
  es el peor día para descubrirlo—.
- No compra nada funcional. Es consistencia, y se pagaría con el presupuesto de
  riesgo justo antes de F5, que toca todo el cálculo de impuestos.

**Lo que haría cambiar la decisión**: F5 no toca estas tablas, pero **F6 sí**
—T-608 construye el ABM de sucursales y terminales, que son de las afectadas—.
Si se corrige, el sitio es ahí: se paga una vez, con el trabajo que de todos
modos abre esos archivos, y con la migración que F6 ya va a escribir. En ese caso
hace falta además subir `FORMATO` en `company_dump.py` y darle un lector de
compatibilidad para los respaldos anteriores.

Mientras tanto, la regla de código en inglés **sigue vigente para todo lo demás**:
esta excepción es de las columnas que ya existen, no una licencia para las nuevas.

---

## 4. Panel de soporte (F3) — hecho el 2026-08-23

Grupo de rutas `/admin` en el mismo despliegue, no una aplicación aparte:
duplicar autenticación y despliegue para cinco pantallas no se paga.

- Solo rol `soporte`, verificado en el servidor en cada `load` y cada acción.
- Su sesión **no tiene compañía**: las pantallas del POS le responden 403.
- *Entrar como* emite un token con el `company_id` de la compañía destino, con
  vencimiento corto y motivo obligatorio, y escribe en `audit_log`. La interfaz
  muestra una franja permanente mientras dure.
- Toda acción de soporte se registra: alta, cambio de estado, entrada.

### 4.1 Quién es soporte

**Una columna: `users.is_support`** (migración 004). El plan decía «soporte es
una persona sin ninguna membresía» y como definición no servía: quien rechaza la
única invitación que tenía también se queda sin ninguna, y quedaría
administrando el producto por descarte. La ausencia de algo no puede ser un
permiso.

La marca vive en `users` y no en `user_companies` porque es una propiedad de la
identidad, como el correo. La primera cuenta se crea con
`bootstrap.py --soporte`, por lo mismo que la primera compañía: no hay API que
pueda otorgar un permiso que todavía nadie tiene.

### 4.2 Cuatro tipos de token

| `tipo` | Lleva `cid` | Dura | Para qué |
|---|---|---|---|
| `transito` | no | 10 min | elegir compañía (RN-26) |
| `sesion` | sí | 8 h | el POS |
| `soporte` | **no** | 8 h | el panel |
| `suplantacion` | sí | **30 min** | *entrar como* (RF-8) |

Que el de soporte no lleve compañía es todo el diseño: el filtro de
`tenancy.py` le hace fallar cerrado cualquier consulta a una tabla de negocio,
así que para ver los datos de un cliente **tiene que** entrar como esa compañía
—que es lo que pide RN-4 y lo que deja rastro—. Las consultas del panel, que
cruzan compañías a propósito, van todas por `crud_support.py` con `sin_filtro`.

El de suplantación no lleva rol: lo pone `auth_dependency` en `admin`. Escribir
el rol en dos sitios es la forma de que un día digan cosas distintas.

### 4.3 El bloqueo por vencimiento va en un solo sitio

`get_current_user` corta toda petición con método que escribe cuando la sesión
es de solo lectura. **Acá y no en cada ruta**, por la misma razón que el filtro
de compañía vive en un escuchador de SQLAlchemy: cuarenta endpoints que hay que
acordarse de tocar no son un control de acceso.

Las dos excepciones están en `ESCRITURA_EN_SOLO_LECTURA` con su motivo escrito
—`/cash/close` por RN-1 y `/auth/locale` porque el aviso de pago hay que poder
leerlo en su idioma—, y `tests/test_suscripcion.py` obliga a que sigan siendo
rutas que existen. El mismo archivo tiene el guardián que importa a futuro: toda
ruta que escriba pasa por `get_current_user` o está declarada con su porqué.

En el POS el bloqueo se adelanta a **una** pantalla, ventas, porque es la única
donde la sorpresa cuesta plata (RN-2). Las demás se quedan con el aviso del
layout: allá lo que se pierde al chocar con el «no» es un clic.

### 4.4 El estado se evalúa en cada petición, no se guarda

`domain/subscription.py` es aritmética pura: estado guardado + fecha + hoy →
qué se puede hacer. Se llama en cada `get_current_user` y viaja al POS por
`/users/me`, **no en el token**. Meterlo en el token lo congelaría hasta el
próximo login, que es lo peor de los dos mundos: bloquea tarde y desbloquea
tarde. Así, un pago que entra hoy le devuelve el POS al cliente en el siguiente
clic.

### 4.5 El alta es una sola función, usada por dos caminos

`crud_company.dar_de_alta` crea las seis filas —compañía, sucursal, terminal,
configuración, identidad y membresía— y la llaman `bootstrap.py` y
`POST /support/companies`. Antes la lista vivía en el guion; copiarla al panel
habría dejado dos altas que se parecen y que dejarán de parecerse el día que
haya una séptima fila.

**Los textos del documento los manda el POS** (T-304). Nacen vacíos en el
dominio (T-816) y el backend no puede escribirlos —no tiene catálogo y no sabe
en qué idioma—, así que el formulario del panel los resuelve con
`initialDocumentTexts(document_locale)` y los envía en `settings`. Es el único
momento en que se conocen las dos cosas a la vez: el idioma del documento y las
palabras.

### 4.6 El API va bajo `/support` y las pantallas bajo `/admin`

Dos nombres para lo mismo, a propósito: `admin` ya es el rol del administrador
de una compañía, y dos cosas distintas con el mismo nombre en el mismo API se
confunden. En la barra de direcciones, en cambio, `/admin` es lo que se lee
bien.

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

#### La tarifa se congela en la línea, no en el producto

`sale_details` recibe `tax_rate` y `tax_amount`, escritos en el momento de
cobrar. **No basta con tener la tarifa en `products`**, por dos razones que son
la misma regla vista de dos lados:

1. La tarifa del producto cambia —Hacienda actualiza el catálogo, o el dueño
   corrige el código CABYS—. Sin congelarla, devolver algo vendido el mes pasado
   usaría la tarifa de hoy. Es exactamente lo que RN prohíbe.
2. Con tarifas mezcladas, la del encabezado deja de servir. Hoy la devolución
   reconstruye la tasa como `tax / subtotal` (`TaxRate.of_sale`), y eso funciona
   mientras toda la venta lleve una sola tarifa. En cuanto se mezclan, ese
   cociente es un **promedio**:

   ```
   venta: 1 medicamento ₡1 000 al 2 %  +  1 arroz ₡1 000 al 13 %
          subtotal ₡2 000 · impuesto ₡150 · promedio 7,5 %

   devolver solo el medicamento →  correcto  1 000 × 1,02 = ₡1 020
                                   promedio  1 000 × 1,075 = ₡1 075
   ```

   ₡55 de más, y ₡55 de menos si lo que se devuelve es el arroz. La caja no
   cuadra y nadie sabe por qué.

`TaxRate.of_sale` no se borra: sigue siendo lo correcto para las ventas
anteriores a esta migración, que tienen una sola tarifa y no tienen la columna.
La devolución usa la tarifa de la línea cuando está, y el cociente del
encabezado cuando no.

#### Y el servidor tiene que verificar por línea

El cálculo del servidor (T-108b) recibe hoy **una** tasa
(`sale_totals(lines, rate)`) y la aplica al subtotal. Con tarifas por línea pasa
a aplicar la de cada una y a sumar. La tolerancia de un céntimo se vuelve más
apretada de lo que parece: con tres tarifas distintas hay tres redondeos donde
antes había uno, así que la tolerancia debe medirse **por documento y no por
línea**, o una venta larga con tarifas mezcladas se rechazaría por acumulación.

---

## 7. Facturación electrónica

### 7.1 Credenciales de Hacienda (entra en F6)

#### Son dos secretos y los dos son por ambiente

Firmar y transmitir son operaciones distintas con credenciales distintas, y
Hacienda las emite por separado para pruebas y para producción
(`docs/hacienda/costa-rica/README.md` §7 y §12):

| | Para qué | Dónde se obtiene |
|---|---|---|
| `.p12` + PIN | Firmar el XML (XAdES-EPES) | ATV → Llave Criptográfica |
| Usuario + contraseña ATV | Token OIDC del IdP, para transmitir | ATV → Credenciales API |

El usuario tiene forma `cpf-01-1234-5678@comprobanteselectronicos.go.cr`, el
`grant_type` es `password` y el `client_secret` va vacío. El `client_id` y el
realm los decide el ambiente: `api-stag`/`rut-stag` contra `api-prod`/`rut`.

**La llave primaria es `(company_id, environment)` y no `company_id`.** El diseño
anterior solo admitía un juego por compañía, y con eso «pasar a producción»
significaba borrar lo de pruebas sin poder volver. Un cliente en integración
tiene los dos a la vez (RN-33).

```sql
CREATE TABLE fe_credentials (
    company_id      INT          NOT NULL,
    environment     VARCHAR(12)  NOT NULL,   -- 'sandbox' | 'production'

    -- Firma -----------------------------------------------------------------
    -- La parte PÚBLICA se guarda siempre y NO es secreta: viaja en el KeyInfo
    -- de cada XML firmado. El `.p12` —que lleva la privada— solo se guarda con
    -- custodia 'local'; con 'vault' la privada vive en Vault y acá no hay nada
    -- que descifrar. Son dos columnas y no una porque son dos contenidos.
    certificate_pem LONGTEXT     NULL,       -- parte pública, sin cifrar
    p12_encrypted   LONGTEXT     NULL,       -- base64 del .p12 cifrado (solo 'local')
    pin_encrypted   VARBINARY(512) NULL,
    key_custody     VARCHAR(12)  NULL,       -- 'local' | 'vault'; NULL = sin certificado
    key_version     TINYINT      NOT NULL DEFAULT 1,
    certificate_name VARCHAR(160) NULL,
    expires_at      DATETIME     NULL,       -- DATETIME y no DATE: el notAfter tiene hora
    cert_uploaded_at DATETIME    NULL,
    cert_uploaded_by INT         NULL,

    -- Transmisión -----------------------------------------------------------
    atv_user        VARCHAR(160) NULL,       -- identificador, NO secreto: se muestra
    atv_password_encrypted VARBINARY(512) NULL,
    atv_updated_at  DATETIME     NULL,
    atv_updated_by  INT          NULL,
    atv_verified_at DATETIME     NULL,       -- última vez que el IdP dio token

    PRIMARY KEY (company_id, environment),
    CONSTRAINT fk_fe_credentials_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
```

**Los nombres van en inglés**, como el resto del código. §3.9 cierra ese punto
diciendo que la excepción de las columnas en español «es de las columnas que ya
existen, **no una licencia para las nuevas**», y esta fase estrena una tabla
entera. El valor del ambiente es `'sandbox'` y no `'pruebas'` porque es el que
el POS ya publica hoy (`settings.eInvoicing.environment`), y tener dos vocablos
para el mismo estado es cómo se pierde una migración.

**Las marcas de tiempo son dos pares** porque son dos secretos con vidas
distintas: rotar la contraseña de ATV en marzo no puede hacer que la pantalla
diga que el certificado se subió en marzo.

**Hereda `TenantMixin`.** Es una tabla de compañía y va con el filtro automático
de `tenancy.py`, que falla cerrado: dejarla fuera la convertiría en la única
tabla de negocio cuya lectura depende de que alguien se acuerde de escribir el
`WHERE`, y lo que se filtraría es un certificado de firma. Dos consecuencias que
hay que escribir porque muerden:

1. El `company_id` del mixin entra en una **clave primaria compuesta**, así que
   se declara con `PrimaryKeyConstraint('company_id', 'environment')` y no con
   `primary_key=True` suelto.
2. **El trabajador de transmisión corre fuera de una petición** (§7.2), donde no
   hay compañía en el contexto. Sin un `with compania(cid)` alrededor de cada
   documento, la primera lectura de credenciales lanza `SinCompania` y la cola
   no avanza nunca. Es la misma trampa que CLAUDE.md ya documenta para los
   objetos expirados después del `commit`.

#### Dónde vive la llave privada: un puerto con dos adaptadores

La decisión no es «Vault sí o no» sino **de quién es el problema**, y eso cambia
con el despliegue. Va detrás de un puerto —`DocumentSigner`— con dos
implementaciones:

```python
class DocumentSigner(Protocol):
    def sign(self, digest: bytes, *, company_id: int, environment: str) -> bytes: ...
```

**La compañía y el ambiente van explícitos y no en un `ContextVar`.** Con estado
escondido, el caso de uso no se puede probar contra «firmá esto con el de
pruebas», y el adaptador de Vault no tendría cómo elegir llave sin heredar el
contexto de la petición — que es justo lo que el trabajador de fondo no tiene.

- **Local.** El `.p12` cifrado con **AES-256-GCM**, llave de 32 bytes en
  `FE_CRYPTO_KEY` y el par `(company_id, environment)` como dato asociado: un
  registro copiado a otra compañía o a otro ambiente no descifra. Se descifra en
  memoria, solo al firmar, y no se escribe a disco. Es lo que corre en la VM de
  un negocio, donde no hay quien administre un Vault.
- **Vault transit.** La llave privada se importa a Vault y **nunca entra en
  memoria de la aplicación**: se le manda el digest y devuelve la firma
  (PKCS#1 v1.5, que es lo que pide XAdES-EPES). Es el despliegue multiempresa, y
  es el que ya usa DetCore
  (`docs/hacienda/costa-rica/recepcion-comprobantes-mensaje-receptor.md` §3.1).

**El nombre de la llave en Vault se DERIVA, no se guarda.** Se calcula en el
servidor a partir de `(company_id, environment)`. Guardarlo como un campo que
alguien pueda escribir sería dejar que el administrador de la compañía 7 apunte
a la llave de la compañía 3 y emita documentos fiscales firmados con el
certificado de otro cliente. Es el equivalente exacto del dato asociado del
AES-GCM: en los dos adaptadores, la identidad de la llave la fija el servidor.

**`key_version` existe para poder rotar sin Vault.** El adaptador local usa una
llave estática, y sin versión en la fila, rotar `FE_CRYPTO_KEY` significa que
todos los clientes vuelvan a subir su certificado. Con versión, es un trabajo de
fondo que recifra fila por fila.

**El arranque falla si `FE_CRYPTO_KEY` no está o no mide 32 bytes.** Sin eso, el
primer aviso llega el día que alguien sube un certificado, que es tarde.

#### Lo que Vault arregla, y el modo de falla que introduce

Lo que gana es exactamente lo flojo del adaptador local: una llave estática no
rota, no deja rastro de cada uso y, si se pierde, obliga a todos los clientes a
volver a subir su certificado. Transit da rotación y **bitácora de cada firma**,
que para una llave que emite documentos fiscales es la mitad del valor.

**El modo de falla nuevo no es «sin internet».** El despliegue de LAN usa el
adaptador local, donde Vault nunca está en el camino, y el hospedado ya necesita
red para que el POS alcance al backend. El riesgo real es **Vault sellado con el
backend arriba**: se sigue vendiendo, se sigue numerando, y la cola crece sin que
nada falle a la vista.

Y tiene reloj. Lo emitido en contingencia tiene un plazo para transmitirse —unos
8 días hábiles— y Hacienda rechaza por antigüedad pasados los 30 días. Un Vault
sellado un viernes por un reinicio, sin quien lo abra hasta el lunes, se come
tres días de ese presupuesto en silencio. **La mitigación es la alarma de
antigüedad de la cola (§7.2), no el desellado**: cualquier cosa que detenga la
firma —Vault, un certificado vencido, un disco lleno— se ve por el mismo sitio.

#### Reglas que no dependen del adaptador

- El `GET` de estado devuelve **los dos ambientes**, no el activo: RF-30 pide ver
  qué le falta a cada uno, y con un objeto singular la pantalla necesitaría dos
  llamadas y no podría decir «producción está listo, pruebas no».
- El archivo, el PIN y la contraseña **no tienen** endpoint de lectura. No existe
  el camino.
- No se registran en bitácora ni en trazas de error. Sí se registra **que** se
  usaron —quién pidió un token, quién reemplazó un certificado—, nunca su
  contenido.
- Subir, reemplazar o quitar credenciales es de **administrador**. Con eso el
  bloqueo por suscripción las alcanza sin tocar nada.
- Probar la conexión (RF-31) pide un token y lo descarta, con tiempo de espera
  explícito —el precedente es el adaptador de CABYS— y distinguiendo los tres
  desenlaces. Guarda `atv_verified_at` para que la pantalla pueda decir
  «verificadas el 3 de septiembre» en vez de obligar a probar a ciegas.

#### El ambiente activo

`fe_credentials` guarda credenciales **por** ambiente; cuál está en uso es otro
dato y vive en la configuración de la compañía, que es donde ya está hoy
(`settings.eInvoicing.environment`). RN-35 —confirmar y registrar el paso a
producción— es un cambio de estado sobre ese dato.

**Y el ambiente viaja también en la fila del documento**, no solo en la del
contador. Sin eso: cinco tiquetes de prueba quedan en cola sin firmar porque el
sandbox estaba lento, al día siguiente el administrador pasa a producción, el
trabajador toma la cola y toma las credenciales vigentes — cinco documentos con
efecto fiscal real que nadie quiso emitir.

#### El respaldo por compañía: lo público sí, los secretos no (decidido el 2026-09-06)

`company_dump.py` tiene un guardián que tumba `pytest` en cuanto aparece una
tabla sin clasificar, así que `fe_credentials` se clasifica **por columna y no
por tabla**, que es lo que el guardián no contemplaba y hay que enseñarle:

| Va en el respaldo | No va |
|---|---|
| `certificate_pem`, `certificate_name`, `expires_at` | `p12_encrypted`, `pin_encrypted` |
| `atv_user`, las marcas de tiempo | `atv_password_encrypted` |
| `environment`, `key_custody` | |

El descarte del `.p12` cifrado no es por RNF-5 —ahí estaría bien, la llave no
viaja—: es porque en otra instalación, con otra `FE_CRYPTO_KEY`, es un archivo
indescifrable que nadie distingue de uno bueno hasta el día de facturar. Lo que
sí viaja es todo lo que puede volver solo, y **al restaurar la pantalla dice qué
falta cargar** (RN-47). Un respaldo que parece completo y no lo es solo se
descubre cuando hace falta.

#### La identificación del emisor vive en `companies` (decidido el 2026-09-06)

Estaba en dos sitios y ninguno alcanzaba solo: `companies.identificacion` la pone
soporte al dar de alta pero es **opcional y sin tipo**, y `business.taxId` +
`business.taxIdType` de Configuración tienen el tipo pero los edita el
administrador del negocio.

Manda `companies`, con una columna `identification_type` nueva, y Configuración
la muestra **de solo lectura** (RN-45, RF-37). El argumento no es de orden sino
de consecuencia: el `.p12` se emite **a esa identificación** y el usuario de ATV
la lleva dentro de su nombre. Un campo editable deja que el negocio la haga
discrepar de su propio certificado, y ahí no se rechaza un comprobante: se
rechazan todos.

**Y esto le pone precio a T-916.** `companies` es de las tablas con columnas en
español, así que agregarle `identification_type` deja `identificacion` e
`identification_type` **una al lado de la otra en la misma tabla**. O se renombra
en la misma migración, o esa mezcla queda escrita.

#### La certificación previa en sandbox se avisa, no se impide (decidido el 2026-09-06)

Hacienda exige emitir una factura, un tiquete y una nota de crédito en pruebas
antes de producción (README §12). En F6 el paso a producción **avisa de los tres
y deja pasar**, con la bitácora de RN-35; la puerta dura entra en F7 (RN-46).

El motivo es que en F6 no existe nada que contar: no hay emisión todavía. Un
candado construido acá nacería cerrado, sin forma de comprobar que abre, y la
primera vez que se ejercitaría sería con un cliente esperando.

#### Riesgo abierto: TRIBU-CR

`docs/hacienda/costa-rica/README.md` §12 deja pendiente confirmar si TRIBU-CR
—que reemplaza a ATV desde octubre de 2025— cambia URLs o credenciales.
Mitigación comprobable: **ambiente, `client_id`, realm y URL base salen de un
solo módulo**, y una prueba tumba `pytest` si el dominio de Hacienda aparece
escrito en cualquier otro sitio. Es el mismo patrón que ya sostiene
`test_error_codes.py`.

### 7.2 Emisión (F7 — la ruta sigue sin decidir)

La ruta —firmar nosotros o pasar por un proveedor autorizado— sigue abierta:

| | Directo | Vía proveedor autorizado |
|---|---|---|
| Firma XAdES-EPES | nuestra | del proveedor |
| Cambios de esquema de Hacienda | los seguimos nosotros | los sigue el proveedor |
| Costo | cero por documento | mensual o por documento |
| Salir a producción | lento | rápido |
| Dependencia | ninguna | fuerte |

**Nada de lo que sigue depende de esa decisión.** El recorrido del documento, sus
estados, la numeración, la contingencia y lo que se guarda son iguales por las
dos rutas; lo que cambia es quién está del otro lado del puerto `EmisorFE`
(`emitir(venta) → {clave, consecutivo, estado}`, `consultar(clave)`).

#### La numeración

El consecutivo son 20 dígitos: **sucursal (3) + terminal (5) + tipo (2) +
secuencia (10)**, y la secuencia es «dentro del tipo». De ahí que el contador
tenga **cinco dimensiones**:

```
(company_id, branch, terminal, document_type, environment) → última secuencia
```

Con menos, la serie nace con huecos. Escenario con un contador por terminal: se
emite un tiquete, luego una factura, luego otro tiquete → los tiquetes van 1, 3,
5 y las facturas 2, 4. Las dos series quedan con saltos, que es exactamente lo
que Hacienda rechaza («consecutivo fuera de orden»).

**El contador se confirma en la misma transacción que el documento.** Un contador
en transacción propia y corta no serializa las cajas, pero una venta que después
falla —por stock, por un total que no cuadra— deja el número consumido y abre un
hueco. Es el defecto 1 del proyecto otra vez, y el `UnitOfWork` que ya existe es
donde se hace comprobable.

**Un rechazo sí deja hueco, y es esperado.** La clave es la llave de idempotencia
de Hacienda: un comprobante rechazado no se reenvía con la misma clave, hay que
emitir otro con consecutivo nuevo. El número del rechazado queda fuera de la
serie aceptada por diseño de Hacienda, no por defecto nuestro, y hay que
documentarlo o el primer rechazo va a parecer un contador roto.

**Arranque de un negocio que ya facturaba** (RN-36 a RN-38): el cliente indica su
oficina y la última secuencia por tipo, y el sistema continúa desde ahí. Solo se
puede subir, queda en bitácora, y una vez que el sistema emitió el contador es
suyo.

**Y hay un consecutivo que ya existe y no sirve para esto.** `sale_number` lo
fabrica hoy **el navegador**, con `yyyyMMddHHmmss` y el reloj del cliente. Dos
cajas cobrando en el mismo segundo chocan contra `UNIQUE (company_id,
sale_number)` y una de las dos ventas se rechaza en la cara del cliente; además
contradice la regla de que la hora la pone el servidor. F7 tiene que decidir si
`sale_number` pasa a ser el consecutivo o convive con él, y en los dos casos
deja de venir del cliente.

#### La clave y la contingencia

La clave son 50 dígitos y su posición 42 es la **situación**: 1 normal, 2
contingencia, 3 sin internet. Esa clave es **contenido obligatorio de la
representación impresa** y se entrega en el mostrador, así que **se decide al
vender**, no al transmitir.

De ahí RN-43: **la contingencia es un modo del negocio**. Si las transmisiones
recientes vienen fallando, el POS está en contingencia y los documentos nuevos
nacen con situación 2; cuando Hacienda vuelve, sale del modo. No se le pregunta
al cajero y no se adivina por documento — y emitir con situación 2 cuando
Hacienda estaba arriba es causa de rechazo, así que la decisión tiene que salir
de un hecho observado y no de una precaución.

**Lo que sí se difiere es la firma**, no la clave. Son cosas distintas: la clave
es aritmética y se arma sin red; la firma necesita la llave y puede esperar al
momento de transmitir. Esa separación es la que hace que el adaptador de Vault
no agregue un modo de falla en el mostrador.

#### El recorrido y sus estados

```
numerado ──> firmado ──> enviado ──> aceptado
                │            │
                │            └──> rechazado        (respuesta final)
                │
                └──> reintentando ──> detenido     (necesita a una persona)
```

Cada uno se ve en la pantalla de facturas (RF-33). `reintentando` muestra el
último intento y el próximo; `detenido` muestra el motivo.

#### Dos ciclos, no uno

Son dos esperas distintas y confundirlas se paga de los dos lados:

| Ciclo | Cuándo | Cadencia |
|---|---|---|
| **Veredicto** | Hacienda ya recibió (202) | 10 s → 30 s → 1 → 2 → 5 min |
| **Reenvío** | No se pudo alcanzar a Hacienda | 5 → 15 → 30 min → … → 72 h |

El primero sale de `docs/hacienda/costa-rica/README.md` §8: tras el 202 hay que
esperar 5–10 s y «en condiciones normales la validación toma segundos». Con la
cadencia del segundo ciclo, una venta que Hacienda resolvió en tres segundos se
vería «pendiente» cinco minutos en la pantalla del cajero.

**Solo lo transitorio se reintenta** (RN-41). Un rechazo es una respuesta. Un
certificado vencido o unas credenciales rotadas son fallas nuestras y se
detienen en el primer intento: hacer backoff 72 horas sobre eso es demorar el
aviso tres días para llegar a la misma conclusión.

**Y agotar los reintentos no es rendirse** (RN-42): el documento pasa a
`detenido`, sigue transmitible a mano, y su antigüedad se ve. **La alarma de
antigüedad de la cola es una pieza, no un detalle**: es lo único que avisa antes
de que se acabe el plazo de contingencia, y lo que hace visible un Vault sellado,
un disco lleno o un certificado que venció el sábado.

#### Por qué polling y no callbacks

Hacienda soporta `callbackUrl` en el `POST /recepcion` y avisa ella, reintentando
tres veces (README §8). Es más barato que consultar. **Pero un POS en la LAN de
una tienda no tiene URL pública**, así que para este producto el mecanismo
primario es la consulta. En un despliegue hospedado el callback sí sirve y el
puerto tiene que admitir los dos sin cambiar el resto.

#### Lo que se guarda

El **XML firmado tal como se envió**, byte por byte —la firma cubre esos bytes,
regenerarlo da otra firma y deja de ser el documento— y la **respuesta de
Hacienda**, que va firmada por ella y es la prueba de la aceptación. Los dos por
**cinco años**, y los dos descargables (RF-34).

Piezas que faltan en cualquiera de las dos rutas: clave de 50 dígitos,
consecutivo de 20 sin huecos, envío asíncrono con consulta de estado, entrega al
receptor por correo con XML y PDF, y modo contingencia para poder cobrar con
Hacienda caída.

---


## 8. Multi-idioma (F8)

Español, inglés y portugués (RNF-2, RN-22, RN-28 a RN-30). El español en
**usted**: el voseo que tiene hoy la interfaz venía de una suposición sobre el
mercado que el dueño del producto corrigió —en Costa Rica el ustedeo es más
común—, y además «Cobrá rápido» le suena extranjero a un usuario mexicano o
colombiano.

### 8.1 Lo que hay que mover

Medido el 2026-08-16 sobre el código real:

| Dónde | Cuánto |
|---|---|
| Nodos de texto en componentes | 223 |
| Atributos (`title`, `placeholder`, `label`, `aria-label`, `hint`) | 205 |
| Mensajes de acciones del servidor | 27 |
| **Mensajes que produce el backend** | **68** |
| Archivos con texto visible | 33 |
| Apariciones de voseo | 48, en 19 archivos |

Los 48 de voseo no se cuentan aparte: los 455 textos del frontend se tocan igual
al extraerlos, así que reescribirlos a usted en la misma pasada no cuesta nada
adicional. Hacerlo después sí, porque habría que volver a abrir los 33 archivos.

### 8.2 Los 68 mensajes del backend son el trabajo de fondo

Hoy FastAPI escribe la frase que ve el cajero:

```python
detail="Solo podés consultar tu propia caja."
detail=f"Stock insuficiente para {nombre}: quedan {e.available} y se piden {e.requested}."
```

Eso no se puede traducir desde el POS. La API pasa a devolver **código y datos**:

```json
{ "code": "insufficient_stock", "product": "Arroz Tío Pelón 1kg",
  "available": 2, "requested": 5 }
```

y el POS arma la frase con su catálogo.

**El trabajo ya está medio hecho y es el pago de F1.** El dominio lanza errores
tipados que llevan exactamente esos datos —`InsufficientStock(product_id,
available, requested)`, `TotalsMismatch(campo, declarado, calculado)`— y quien
los convierte en texto es el adaptador (`crud_*`). Cambiar el adaptador para que
emita el código en vez de la frase es un archivo por flujo, no una cacería por
todo el backend.

Con el código de error viajando, el mensaje del backend deja de ser un `detail`
suelto: se vuelve un contrato tan estable como el resto del API, y eso hace
posible probar «esta situación devuelve este código» sin comparar cadenas.

### 8.3 Dónde vive el idioma

```sql
ALTER TABLE companies ADD COLUMN locale       CHAR(5) NOT NULL DEFAULT 'es';
ALTER TABLE companies ADD COLUMN document_locale CHAR(5) NOT NULL DEFAULT 'es';
ALTER TABLE users     ADD COLUMN locale       CHAR(5) NULL;
```

- `companies.locale` — el idioma con el que arranca quien entra a esa compañía.
- `users.locale` — lo que esa persona prefiera. En nulo, hereda el de la compañía.
- `companies.document_locale` — **el idioma de la factura, que no es el de la
  pantalla** (RN-29). La factura es para el cliente y para Hacienda: una
  compañía costarricense emite en español aunque su cajero use el POS en
  portugués.

Las tres columnas entran en la migración de F2. No porque F2 las necesite, sino
porque una migración sobre tablas con datos es cara y hacer dos donde cabe una
es trabajo regalado.

### 8.4 Cómo se resuelve el idioma en cada petición

El `locale` efectivo entra en el JWT junto con la compañía y el rol, y de ahí lo
lee el `load` del layout. Así una pantalla nunca tiene que preguntarlo: llega ya
resuelto, igual que la moneda.

El orden es: lo que eligió la persona, si no lo de la compañía, si no `es`.

### 8.5 Biblioteca

Los criterios, en orden:

1. **Que funcione en el servidor.** El POS renderiza en SvelteKit y las acciones
   producen mensajes; una biblioteca que solo viva en el navegador deja fuera la
   mitad.
2. **Que el catálogo se compruebe al compilar.** Una clave que falta tiene que
   romper `npm run check`, no aparecer como `undefined` en la pantalla del
   cajero.
3. **Sin peso en el arranque.** El POS se abre en una caja modesta.

**Paraglide (Inlang)** es el candidato principal: compila los catálogos a
funciones, así que las claves quedan tipadas y solo viaja lo que se usa. La
alternativa es `typesafe-i18n`. La decisión se cierra al empezar la fase, con una
prueba de las dos sobre la pantalla de ventas —que es la más cargada— y no antes:
el ecosistema se mueve y elegir hoy por leer documentación es elegir a ciegas.

### 8.6 Lo que ya es independiente del idioma, y lo que no

**Ya lo es.** La moneda y el impuesto salen de Configuración desde el principio,
no del idioma. Es lo correcto: un negocio en Costa Rica que atiende en inglés
sigue cobrando en colones. Lo mismo el separador de miles.

**Todavía no.** `ui/format.ts` formatea fechas fijo en es-CR: `formatDate`,
`formatDateTime` y los nombres de mes salen escritos a mano. Pasan a depender
del locale.

**Los documentos.** Las tres plantillas llevan sus rótulos —«Factura»,
«Subtotal», «IVA», «Gracias por su compra»— dentro del componente. Se traducen
con el `document_locale`, no con el de la pantalla.

### 8.7 Cuándo hacerlo

**Cuanto antes, y la razón es aritmética.** F3 agrega el panel de soporte, F4 las
categorías de dos niveles, F5 el buscador de CABYS y F6 la pantalla del
certificado. Cada pantalla escrita antes de la extracción es una pantalla que
hay que volver a abrir después.

Lo mínimo razonable: que **el mecanismo exista antes de F3**, aunque los
catálogos de inglés y portugués se llenen más tarde. Escribir pantallas nuevas
con `t('ventas.cobrar')` desde el primer día cuesta lo mismo que escribirlas con
la cadena adentro; convertirlas después, no.

---

## 9. Fases

| Fase | Qué deja | Terminado cuando |
|---|---|---|
| **F0** Repositorio ✅ | `frontend/`, `backend/`, sin clones de referencia | El sistema levanta igual y no queda ninguna referencia a las rutas viejas |
| **F1** Arquitectura y pruebas ✅ | Capas, puertos, y la infraestructura de pruebas con cobertura exigida | El dominio no importa nada, los invariantes de `progress.json` siguen dando igual y la build se cae si baja la cobertura |
| **F2** Multiempresa ✅ | `company_id` en todo, filtro automático de lectura y sellado de escritura, login de dos pasos, migración | Las pruebas de cruce entre compañías dan 404 en todos los endpoints —y se ponen rojas si se desactiva el filtro |
| **F3** Soporte | Panel `/admin`, planes, estados, bitácora | Se puede dar de alta una compañía y operarla de punta a punta |
| **F4** Categorías | Dos niveles en catálogo, ventas e inventario | Un repuestero y un súper organizan su catálogo sin tocar código |
| **F5** Impuesto y CABYS | Tarifa por producto, búsqueda de CABYS, totales por línea | Una venta con 13 %, 2 % y 0 % cuadra y desglosa bien |
| **F6** Preparación FE | Certificado y credenciales ATV cifrados **por ambiente**, sucursales, terminales, actividad, arranque del consecutivo | Se suben el `.p12` y las credenciales de los dos ambientes, se ve el estado de cada uno, se prueba la conexión, se pasa a producción con confirmación y bitácora, y no hay forma de leer de vuelta ni el archivo ni el PIN ni la contraseña |
| **F7** Emisión | La ruta sigue pendiente; **el recorrido no depende de ella**: numeración, estados, consulta, contingencia y archivo | Una venta se emite, se ve pasar por sus estados hasta aceptada, y su XML firmado y la respuesta de Hacienda se pueden descargar |
| **F8** Multi-idioma | Español, inglés y portugués; el backend deja de escribir texto | Los tres catálogos tienen las mismas claves y la build se cae si alguien escribe una cadena dentro de un componente |
| **F10** Compras y cuentas por pagar ← *se ejecuta antes que F6* | Módulos por plan; proveedores; la compra como entrada con documento, condición de pago y crédito fiscal por línea; costo promedio; abonos y antigüedad | Una factura XML de un proveedor entra como compra a crédito, su IVA aparece en el reporte por tarifa, un abono en efectivo sale de la caja y el arqueo cuadra |
| **F11** Contabilidad ← *se ejecuta antes que F6* | Catálogo por compañía desde plantilla, asientos automáticos en la misma transacción, periodos con cierre, libros y borrador del D-104 | La venta 3×1450 deja un asiento que balancea, el mes se cierra, y una escritura con fecha adentro responde con código |
| **F12** Planilla | Empleados, tasas con vigencia, corridas congeladas, aguinaldo, vacaciones, liquidación, archivo para la CCSS y asiento de la corrida | Una corrida de dos empleados se paga, se cambia una tasa con vigencia futura y la boleta reimpresa da lo mismo |

**F1 fue primero y no era opcional.** Todo lo que sigue toca dinero, existencias o
aislamiento entre compañías, y sin pruebas que fijen el comportamiento actual no
hay forma de saber si un cambio rompió algo: los invariantes de `progress.json`
se verifican hoy a mano, una vez, y eso no escala a seis fases más. Además, F2
mete un filtro por compañía en la capa de persistencia, que es justamente la
capa que F1 crea.

F4 y F5 pueden ir en paralelo. F6 depende de F2, que ya está.

**F8 lleva número alto pero conviene adelantarla.** El orden de las fases es de
dependencia, no de calendario, y multi-idioma no depende de ninguna: solo de que
existan las columnas, que entran con la migración de F2. Lo que sí importa es
que el **mecanismo** esté antes de F3, porque F3, F4, F5 y F6 agregan pantallas
y cada una escrita con la cadena adentro hay que volver a abrirla. Llenar los
catálogos de inglés y portugués puede esperar; escribir con `t('…')` desde el
primer día, no.

**El orden de ejecución es F10 → F11 → F6 → F7 → F12**, y no el de los
números. La tabla va numerada porque los números no se mueven —F8 ya sentó el
precedente: se ejecutó antes que F5 y se quedó en su casilla—; lo que manda es
este párrafo.

El primer borrador ponía los tres módulos después de F7, con el argumento de
que la emisión es lo único legalmente obligatorio. El argumento es cierto y
por eso mismo **no vende**: como todos los negocios están obligados, todos ya
lo resolvieron de alguna forma antes de conocernos. Emitir no gana el trato,
evita perderlo. Nadie está obligado a llevar su contabilidad en un programa, y
ahí es donde el producto cobra más y donde el cliente se queda: los libros de
tres años no se mudan de sistema.

Lo que sí hay que mirar es **de qué depende cada cosa**, y ahí no hay
conflicto: contabilidad necesita el IVA por tarifa (F5, hecho), el crédito
fiscal y el costo del producto (F10). Nada de F6 ni de F7. La compra desde XML
lee el comprobante **del proveedor**, que existe se emita o no, y el asiento
referencia la venta por su `id`, no por su número, así que cuando F7 cambie la
numeración (T-706) el libro no se entera.

Entre los módulos el orden sigue siendo de dependencia: el crédito fiscal sale
de las compras, así que F10 va antes que F11.

**F12 se queda de última, y a propósito.** No comparte nada con el POS —ni
productos, ni ventas, ni caja—, su soporte es estacional (todos necesitan el
aguinaldo la misma semana de diciembre) y es lo único que ata el producto a un
país. Adelantar contabilidad y adelantar planilla no son la misma apuesta.

**Lo que decide cuánto cuesta postergar F6 y F7 es T-701**, no su número: vía
proveedor autorizado, F7 es un adaptador detrás de `EmisorFE`; directo, son
XAdES, el IdP de Hacienda y seguirle los cambios de esquema. Mientras esa
decisión siga abierta, F7 no es una fase grande sino una de tamaño
desconocido, y eso es lo que la manda al final.

Y no hay F9: el número de tarea lleva la fase —T-5nn, T-6nn— y el 9 lo ocupa
Transversal (T-9nn) desde F2. Saltarlo cuesta una línea; renumerar veinte
tareas cerradas, no.

---

## 10. Riesgos

| Riesgo | Mitigación |
|---|---|
| Una consulta sin filtro filtra datos entre compañías | Filtro automático en el ORM + pruebas de cruce en todos los endpoints |
| `with_loader_criteria` no cubre el SQL agregado de reportes ni los UPDATE masivos | Filtro escrito a mano en `crud_report.py`, con prueba propia. Revisar en cada agregado nuevo |
| El refactor de F2 toca todos los archivos y puede romper lo que ya funciona | Las pruebas de F1 son la red. Por eso F1 va antes: los invariantes de `progress.json` dejan de comprobarse a mano y pasan a correr solos |
| Reorganizar por capas (F1) es mover mucho código sin cambiar comportamiento, que es donde se cuelan los errores silenciosos | Pruebas de caracterización **antes** de mover nada, y se mueve capa por capa, no todo junto |
| La cobertura del 100 % empuja a escribir pruebas de relleno para pasar el umbral | El umbral cubre solo dominio y aplicación, que son código puro y de reglas. Ahí una función sin prueba es una regla sin verificar, no burocracia |
| `FE_CRYPTO_KEY` se pierde | **El arranque falla si no está o no mide 32 bytes**, para no enterarse al firmar. `key_version` en la fila permite rotarla como trabajo de fondo en vez de pedirle a cada cliente que vuelva a subir su certificado. Se guarda fuera del repositorio y fuera de la base |
| **Vault sellado con el backend arriba**: se sigue vendiendo y numerando, y la cola de transmisión crece sin que nada falle a la vista | La alarma de antigüedad de la cola (§7.2). No es el desellado: cualquier cosa que detenga la firma —Vault, un certificado vencido, un disco lleno— se ve por el mismo sitio, y avisa antes de que se acabe el plazo de contingencia |
| **TRIBU-CR** cambia URLs o credenciales de ATV (README §12 lo deja pendiente de confirmar) | Ambiente, `client_id`, realm y URL base salen de **un solo módulo**, y una prueba tumba `pytest` si el dominio de Hacienda aparece escrito en otro sitio |
| **El certificado vence sin que nadie mire** y la emisión se detiene | Aviso 30 días antes (T-606) y estado `detenido` con su motivo en la lista de RF-35. `expires_at` guarda la hora, no solo el día |
| Diferir la firma alarga la ventana entre emitir y transmitir, y la contingencia tiene plazo | El plazo se vigila explícitamente: la antigüedad de la cola es visible y alarma antes de los 8 días hábiles. Hacienda además rechaza por antigüedad mayor a 30 días |
| El API de CABYS no responde | Caché local; la venta nunca depende de él |
| Borrar los clones de referencia | Están en GitHub y el análisis quedó escrito en `progress.json` y en `backend/README.md` |
| El impuesto por línea toca dinero ya verificado | Los invariantes de `progress.json` se recalculan y se documentan de nuevo |
| Un mapeo incompleto detiene una venta, porque el asiento va en la misma transacción | La cuenta «por clasificar» (RN-59): el asiento siempre existe y balancea; lo que falta se ve en rojo en contabilidad, no en la caja |
| Una tasa de la CCSS o un tramo de renta cambia y nadie lo siembra | Tablas con vigencia y `verified_at` visibles (RN-67); la pantalla de planilla avisa cuando la vigencia más reciente tiene más de seis meses; soporte actualiza para todas las compañías desde el panel |
| Planilla ancla el producto a un país | Las fórmulas reciben las tablas por parámetro y no conocen ningún porcentaje; el país es una columna. Otro país es sembrar, no programar —aunque no se construya— |
| El promedio ponderado con existencias negativas o con una compra anulada | Regla escrita y probada: existencia ≤ 0 → el costo es el de la compra; anular no deshace el promedio (RN-57) y la siguiente compra lo corrige. Está en la tabla de casos de `weighted_average_cost` |
| El formato del archivo de la CCSS no se conoce hasta leer la especificación | T-1211 empieza por leer el material oficial, como T-702 con los XSD; el archivo sale de un adaptador con prueba contra un ejemplo real |
| Cerrar un periodo por error, sin poder reabrir | La confirmación muestra el resumen del periodo y el saldo de «por clasificar» antes de cerrar; lo que quede mal se ajusta en el siguiente, que es lo que un contador hace de todos modos |
| `sales.payment_method` es texto libre y el mapeo necesita un conjunto cerrado | T-1104 lo cierra a un catálogo de valores antes de mapear; un valor desconocido va a «por clasificar», no rompe la venta |

---

## 11. Módulos por plan (F10–F12)

Compras, contabilidad y planilla se venden aparte, y el sistema ya tiene el
lugar donde se dice qué se vende: `plans`. `factura_electronica` es una bandera
del plan desde F2, y estos tres son tres banderas más. No hay tabla nueva ni
interruptor por compañía (RN-51): dos sitios para la misma verdad —el plan
dice una cosa y la compañía otra— es donde se separan, y el que mira soporte
es el plan.

```sql
-- 008-modulos-por-plan.sql
ALTER TABLE plans
    ADD COLUMN purchases  TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN accounting TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN payroll    TINYINT(1) NOT NULL DEFAULT 0;
```

Las tres en inglés: la excepción de §3.9 es de las columnas que ya existen, no
una licencia para las nuevas (T-601). `factura_electronica` se queda como está
por la misma decisión.

**Cómo se aplica.** Una dependencia `require_module("accounting")`, al lado de
`get_current_user`, que lee el plan de la compañía **en cada petición**. No va
en el token por la misma razón que el estado de la suscripción (§4.4): ahí
quedaría congelado hasta el siguiente login, y el cliente que acaba de subir
de plan tendría que salir y volver a entrar para ver lo que pagó. Se aplica a
las **escrituras** de las rutas del módulo; las lecturas quedan libres (RN-50),
porque lo que ya existe es de la compañía y tiene que poder consultarse y
exportarse siempre. La respuesta es `403` con `module_not_in_plan` y
`{"module": "accounting"}` —el token vale, lo que no vale es para esto—, igual
que las dos puertas de soporte.

**En el POS**, la carga que ya trae el estado de la suscripción trae también
`modules: {purchases, accounting, payroll}`; el `+layout.server.ts` arma la
navegación con eso, y cada `action` de un módulo pasa por `requireModule(...)`
además de `requireAdmin`. Esconder la entrada del menú es cortesía; el
servidor es el control.

**En el panel de soporte**, el formulario de planes gana las tres casillas y
el listado de compañías (RF-5) muestra los módulos de cada una. Cambiar el plan
de una compañía ya queda en bitácora (RF-7); no hace falta nada nuevo.

**En el simulado**, el plan de la primera compañía trae los tres módulos y el
de la segunda ninguno: así la prueba de punta a punta tiene con qué comprobar
el rechazo sin dar de alta nada.

---

## 12. Compras y cuentas por pagar (F10)

### 12.1 La compra es la entrada de mercadería

`stock_entries` ya es un documento y no un ajuste: guarda proveedor (como
texto), número de factura, quién y cuándo, y se puede anular. Le faltan tres
cosas —a quién de verdad, con qué condición de pago y con qué impuesto por
línea— y con ellas es una compra (RN-52). Se extiende esa tabla en vez de crear
`purchases` por tres razones:

1. El lector de XML de Hacienda (`lib/server/import/hacienda.ts`) **ya produce
   una entrada** a partir de la factura del proveedor, y el invariante «entrada
   XML 79 800» la fija. Con una tabla nueva habría que mantener dos caminos que
   hacen lo mismo.
2. La anulación ya existe y recorre las líneas para revertir el stock. Una
   compra anulada tiene que revertir lo mismo más la cuenta por pagar.
3. Dos tablas son dos verdades: una entrada con compra y una compra sin
   entrada son estados que no significan nada y que alguien tendría que
   impedir.

Una entrada con `supplier_id` nulo sigue siendo una entrada: las que ya
existen, las de ajuste, las de un proveedor que no se quiso registrar. No
generan cuenta por pagar ni crédito fiscal y el reporte de compras las deja
fuera. La columna `supplier` de texto se conserva para leer el histórico; las
compras nuevas la llenan con el nombre del proveedor por si el registro se
desactiva.

### 12.2 Modelo de datos

```sql
-- 009-compras.sql
CREATE TABLE suppliers (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    company_id          INT          NOT NULL,
    identification_type CHAR(2)      NULL,       -- 01/02/03/04, la lista de Hacienda (T-621)
    identification      VARCHAR(30)  NULL,       -- NULL: proveedor informal
    name                VARCHAR(160) NOT NULL,
    email               VARCHAR(160) NULL,
    phone               VARCHAR(30)  NULL,
    payment_terms_days  INT          NOT NULL DEFAULT 0,   -- 0 = contado
    is_active           TINYINT(1)   NOT NULL DEFAULT 1,
    created_at          DATETIME     NOT NULL,
    -- La misma identificación es el mismo proveedor: el XML llega con ella y es
    -- como se lo reconoce sin preguntarle a nadie. NULL no choca con NULL.
    UNIQUE KEY uq_suppliers_identification (company_id, identification),
    INDEX idx_suppliers_name (company_id, name),
    CONSTRAINT fk_suppliers_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

ALTER TABLE stock_entries
    ADD COLUMN supplier_id   INT           NULL,             -- NULL: entrada, no compra (RN-52)
    ADD COLUMN document_key  CHAR(50)      NULL,             -- clave de Hacienda, cuando hay XML
    ADD COLUMN document_date DATE          NULL,
    ADD COLUMN payment_terms VARCHAR(10)   NOT NULL DEFAULT 'cash',   -- 'cash' | 'credit'
    ADD COLUMN due_date      DATE          NULL,
    ADD COLUMN subtotal      DECIMAL(12,2) NOT NULL DEFAULT 0,
    ADD COLUMN tax           DECIMAL(12,2) NOT NULL DEFAULT 0,
    -- total_cost ya existe y pasa a valer subtotal + tax. El nombre se queda:
    -- lo leen el lector de XML, la anulación y una prueba de caracterización.
    ADD INDEX idx_stock_entries_supplier (company_id, supplier_id, status),
    ADD INDEX idx_stock_entries_due (company_id, due_date),
    ADD CONSTRAINT fk_stock_entries_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers (id);

ALTER TABLE stock_entry_details
    ADD COLUMN tax_rate   DECIMAL(5,2)  NOT NULL DEFAULT 0,    -- la del documento (RN-53)
    ADD COLUMN tax_amount DECIMAL(12,2) NOT NULL DEFAULT 0;

-- El producto no sabía cuánto costó. Promedio ponderado, a dos decimales como
-- todo lo demás (RN-54).
ALTER TABLE products
    ADD COLUMN cost DECIMAL(12,2) NOT NULL DEFAULT 0;

CREATE TABLE supplier_payments (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    company_id       INT           NOT NULL,
    supplier_id      INT           NOT NULL,
    entry_id         INT           NOT NULL,     -- el abono es a UNA compra (RN-55)
    amount           DECIMAL(12,2) NOT NULL,
    method           VARCHAR(20)   NOT NULL,     -- 'cash' | 'transfer' | 'other'
    reference        VARCHAR(100)  NULL,         -- número de transferencia, cheque
    cash_movement_id INT           NULL,         -- si salió de la caja (RN-56)
    user_id          INT           NOT NULL,
    paid_at          DATETIME      NOT NULL,     -- la pone el servidor
    INDEX idx_supplier_payments_entry (entry_id),
    INDEX idx_supplier_payments_supplier (company_id, supplier_id, paid_at),
    CONSTRAINT fk_sp_company  FOREIGN KEY (company_id)       REFERENCES companies (id),
    CONSTRAINT fk_sp_supplier FOREIGN KEY (supplier_id)      REFERENCES suppliers (id),
    CONSTRAINT fk_sp_entry    FOREIGN KEY (entry_id)         REFERENCES stock_entries (id),
    CONSTRAINT fk_sp_movement FOREIGN KEY (cash_movement_id) REFERENCES cash_movements (id),
    CONSTRAINT fk_sp_user     FOREIGN KEY (user_id)          REFERENCES users (id_user)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
```

El abono es **por compra** y no «a cuenta» a propósito: un abono a cuenta que
se reparte entre facturas (PEPS de deudas) necesita una regla de reparto, y la
regla de reparto es lo primero que un proveedor discute. Con el abono atado a
un documento, el saldo de cada factura es un hecho y el del proveedor es una
suma.

### 12.3 Dominio y aplicación

`domain/purchases.py`, puro, con su tabla de casos:

| Función | Regla | Casos que la prueban |
|---|---|---|
| `weighted_average_cost(stock, cost, qty, unit_cost)` | RN-54; existencia ≤ 0 → `unit_cost` | 10 u a 100 + 10 u a 120 → 110; 0 u + 5 a 80 → 80; −3 u + 10 a 50 → 50; redondeo a 2 |
| `purchase_totals(lines)` | RN-53: suma línea por línea, por tarifa | las mismas tablas de `sale_totals` (§6.3), con tarifas mezcladas |
| `remaining_balance(total, payments)` | RN-55 | sin abonos → total; con abonos → resta; nunca negativo |
| `apply_payment(balance, amount)` | RN-55: lanza `PaymentExceedsBalance` | 800 sobre 1 000 → 200; 1 001 sobre 1 000 → error |
| `aging_bucket(due_date, today)` | RF-44 | 0–30, 31–60, 61–90, > 90; sin vencimiento → 0–30 |

Puertos: `SupplierRepository`, `SupplierPaymentRepository`; `StockEntryRepository`
gana los campos nuevos. Casos de uso:

- `RegisterPurchase` **es** `RegisterStockEntry` con proveedor, documento y
  condición: aplica el stock igual que hoy, actualiza `products.cost` con el
  promedio, calcula el vencimiento desde `payment_terms_days` y deja la cuenta
  por pagar implícita (saldo = total − abonos). Con condición de contado, el
  pago se registra en el mismo acto como un abono por el total.
- `PaySupplier`: comprueba el saldo; si el método es efectivo, exige un turno
  de caja abierto en la terminal de la sesión y escribe el movimiento de salida
  con motivo —«Pago a ‹proveedor›, factura ‹n›»— antes de guardar el abono
  (RN-56). Sin turno abierto, `cash_session_required`.
- `VoidPurchase`: rechaza si hay abonos (`purchase_has_payments`); si no,
  revierte el stock como la anulación de hoy, marca `anulada`, y escribe en
  bitácora. **No recalcula el costo promedio**: hacerlo exige rehacer todas las
  compras posteriores del mismo producto en orden, y el promedio móvil no
  guarda de dónde vino cada céntimo. La siguiente compra lo corrige sola; la
  pantalla lo dice al anular.

### 12.4 API y pantallas

```
GET  /suppliers                      lista, con saldo
POST /suppliers · PUT /suppliers/{id}  admin
POST /purchases                      admin · la vista previa confirmada
POST /purchases/from-xml             admin · el BFF ya parseó: manda el
                                     proveedor y las líneas con su impuesto
GET  /purchases?supplier=&from=&to=  cualquiera con el módulo
POST /purchases/{id}/void            admin · {reason}
POST /purchases/{id}/payments        admin · {amount, method, reference}
GET  /payables?supplier=             saldos por compra y antigüedad
GET  /reports/purchases?from=&to=    base e impuesto por tarifa (RF-45)
```

Las rutas de entradas que ya existen siguen: una entrada sin proveedor es un
`POST /purchases` sin `supplier_id`. En el POS, la pantalla de entradas de
`/inventario` **es** la de compras: gana el selector de proveedor, el documento,
la condición de pago y la tarifa por línea, y conserva la vista previa (§8,
regla 6). Nuevas: `/compras/proveedores` y `/compras/cuentas-por-pagar`
(saldos, antigüedad, abonar). El reporte de compras va con los demás, en
`/dashboard`.

El lector de XML pasa a extraer, además de las líneas: `Emisor` (tipo y número
de identificación, nombre), `Clave`, `NumeroConsecutivo`, `FechaEmision`,
`CondicionVenta` (`01` contado, `02` crédito) con `PlazoCredito`, y por línea
`Impuesto/Tarifa` y `Impuesto/Monto`. Si el proveedor no existe, la vista
previa lo muestra como «nuevo» y se crea al confirmar (RF-42).

### 12.5 Códigos de error

`supplier_inactive`, `purchase_has_payments`, `payment_exceeds_balance`,
`cash_session_required`, `duplicate_supplier_document` —la regla de la factura
duplicada que ya existe (índice `idx_stock_entries_document`) pasa a ser por
proveedor: el mismo número de dos proveedores distintos es normal—. Cada uno
en los cuatro lugares.

**Y cuatro más, que aparecieron al escribir T-1007** y que esta lista no tenía:

| Código | Cuándo | Datos |
|---|---|---|
| `supplier_not_found` | Pedir o editar uno que no existe —o que es de otra compañía, que para esta sesión es lo mismo (RNF-1)— | `supplier_id` |
| `supplier_identification_taken` | La misma identificación es el mismo proveedor: dos fichas del mismo mayorista se reparten sus compras y ninguno de los dos saldos es el que se le debe | `identification`, `name` de quien ya la tiene |
| `invalid_identification_type` | No es uno de los cuatro de Hacienda | `identification_type` |
| `identification_required` | Vino el tipo sin el número: un «02» sin cédula jurídica no sirve ni para emitir ni para reconocerlo en un XML | — |

Los dos últimos van **sin prefijo de proveedor** a propósito: `companies`
(T-621) y `clients` (T-617) tienen el mismo par de columnas y les sirve el
mismo «no».

### 12.6 Decisiones

| Tema | Qué se decidió | Por qué | Estado |
|---|---|---|---|
| Compra vs. entrada | La compra es la entrada, extendida | §12.1: un solo camino, una sola anulación, el lector de XML ya está | tomada |
| Costeo | Promedio ponderado móvil, en el producto | PEPS exige capas por lote y devoluciones que las deshacen; con 5 000 productos es donde se descuadra. Hacienda acepta los dos | tomada |
| Abonos | Por compra, no a cuenta | El reparto es lo primero que se discute; atado al documento, el saldo es un hecho | tomada |
| Efectivo | Sale de la caja abierta o no sale | RN-56: lo que no está en un turno no aparece en un arqueo | tomada |
| Anular | Solo sin abonos; no deshace el promedio | Rehacer el promedio hacia atrás exige rehacer la historia; la siguiente compra lo corrige | tomada |
| Devoluciones a proveedor | Fuera, con la compra preparada para recibirlas | Tres efectos a la vez (stock, saldo, crédito fiscal) y ningún caso real todavía | tomada |

### 12.7 Costes medidos antes de empezar

- `test_esquema.py`: dos tablas y tres `ALTER`, modelo y migración iguales.
- `test_aislamiento.py`: nueve rutas nuevas que declarar y probar.
- `test_error_codes.py`: cinco códigos, cuatro lugares cada uno.
- `test_ports.py`: dos puertos nuevos y uno que cambia de firma.
- `company_dump.py`: `suppliers` y `supplier_payments` **viajan**; se clasifican
  en el mismo commit que las crea.
- Cobertura: `domain/purchases.py` nace con su tabla de casos.
- El simulado: nueve endpoints, proveedores y una compra a crédito en el seed,
  `SEED_VERSION` sube.
- Catálogo `purchases.json` en `messages/es/` **y** en `project.inlang/settings.json`.
- El invariante «entrada XML 79 800» se conserva: el lector agrega campos, no
  cambia cantidades. `test_characterization.py` lo vigila.

---

## 13. Contabilidad (F11)

### 13.1 El asiento va en la misma transacción, y nunca falta

Había dos formas de generar los asientos automáticos: **en la misma
transacción** del evento, o como una **proyección** posterior que lee los
eventos y escribe el libro. La proyección tiene una virtud real —se puede
borrar y rehacer cuando se corrige el mapeo— y un defecto que la descarta:
admite el estado «venta sin asiento», que es exactamente lo que un libro no
puede tener. Un cajero que vende a las 11:59 y un contador que cierra el mes a
las 12:00 no pueden depender de que una tarea de fondo haya corrido.

La objeción a la transacción es que un mapeo incompleto detendría la venta, y
eso viola RNF-4. La salida es que el mapeo **no pueda estar incompleto**: cada
papel que un evento necesita y no tiene cuenta asignada va a una cuenta de
sistema, **«por clasificar»** (RN-59). El asiento balancea siempre, existe
siempre, y el contador ve en rojo un saldo que no debería existir. Corregirlo
es un asiento de ajuste que mueve ese saldo a la cuenta correcta, y eso
recupera lo bueno de la proyección sin su agujero.

Otras cuatro decisiones de fondo:

- **Empieza en una fecha** (RN-60). Las ventas anteriores no tienen costo
  congelado; reconstruirlas sería inventar. Los saldos iniciales entran por un
  asiento de apertura que el contador dicta.
- **Periodos mensuales, sin reabrir** (RN-61). Reabrir es la puerta por donde
  un balance ya entregado deja de coincidir con el libro. Lo que quedó mal se
  ajusta en el siguiente, que es lo que un contador hace de todos modos.
- **La retención y la comisión de tarjetas no se estiman al vender.** La venta
  con tarjeta va a «tarjetas por cobrar» por su bruto; cuando el adquirente
  liquida, el contador registra la comisión y la retención con el monto real.
  Un porcentaje adivinado produce un número que después no coincide con el
  banco, y conciliar dos números que nunca fueron iguales es peor que asentar
  uno tarde.
- **Exportación en CSV**, no en Excel: cualquier programa contable lo importa
  y el POS no gana una dependencia.

### 13.2 Modelo de datos

```sql
-- 010-contabilidad.sql
CREATE TABLE accounts (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT          NOT NULL,
    code       VARCHAR(20)  NOT NULL,     -- '1.1.01'; jerárquico por texto
    name       VARCHAR(120) NOT NULL,
    -- 'asset' | 'liability' | 'equity' | 'income' | 'cost' | 'expense'
    kind       VARCHAR(10)  NOT NULL,
    parent_id  INT          NULL,
    is_system  TINYINT(1)   NOT NULL DEFAULT 0,   -- la usa el mapeo: no se borra (RN-64)
    is_active  TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_accounts_code (company_id, code),
    CONSTRAINT fk_accounts_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_accounts_parent  FOREIGN KEY (parent_id)  REFERENCES accounts (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Qué cuenta usa cada papel de cada evento. Un evento tiene varios papeles: la
-- venta en efectivo usa 'cash', 'sales_13', 'vat_payable', 'cogs' e 'inventory'.
CREATE TABLE account_mappings (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT         NOT NULL,
    -- 'sale' | 'return' | 'cash_close' | 'cash_movement' | 'purchase' |
    -- 'supplier_payment' | 'payroll'
    event      VARCHAR(40) NOT NULL,
    -- 'cash', 'cards_receivable', 'sales_13', 'vat_payable', 'vat_credit',
    -- 'inventory', 'cogs', 'payables', 'cash_over', 'cash_short', …
    role       VARCHAR(40) NOT NULL,
    account_id INT         NOT NULL,
    UNIQUE KEY uq_account_mappings (company_id, event, role),
    CONSTRAINT fk_am_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_am_account FOREIGN KEY (account_id) REFERENCES accounts (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE accounting_periods (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT         NOT NULL,
    year       SMALLINT    NOT NULL,
    month      TINYINT     NOT NULL,
    status     VARCHAR(10) NOT NULL DEFAULT 'open',   -- 'open' | 'closed'
    closed_at  DATETIME    NULL,
    closed_by  INT         NULL,
    UNIQUE KEY uq_accounting_periods (company_id, year, month),
    CONSTRAINT fk_ap_company FOREIGN KEY (company_id) REFERENCES companies (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE journal_entries (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    company_id       INT          NOT NULL,
    period_id        INT          NOT NULL,
    entry_number     INT          NOT NULL,      -- correlativo por compañía, sin huecos
    entry_date       DATE         NOT NULL,
    -- 'auto' | 'manual' | 'adjustment' | 'opening'
    kind             VARCHAR(12)  NOT NULL,
    -- 'sale' | 'return' | 'cash_session' | 'cash_movement' | 'stock_entry' |
    -- 'supplier_payment' | 'payroll_run'
    source_type      VARCHAR(20)  NULL,
    source_id        INT          NULL,
    adjusts_entry_id INT          NULL,          -- el que corrige (RN-61)
    description      VARCHAR(255) NOT NULL,
    user_id          INT          NOT NULL,
    created_at       DATETIME     NOT NULL,
    UNIQUE KEY uq_journal_entries_number (company_id, entry_number),
    -- Un evento, un asiento automático. La anulación de una venta no lo edita:
    -- escribe uno de ajuste que lo revierte.
    UNIQUE KEY uq_journal_entries_source (company_id, source_type, source_id, kind),
    INDEX idx_journal_entries_period (period_id, entry_date),
    CONSTRAINT fk_je_company FOREIGN KEY (company_id)       REFERENCES companies (id),
    CONSTRAINT fk_je_period  FOREIGN KEY (period_id)        REFERENCES accounting_periods (id),
    CONSTRAINT fk_je_adjusts FOREIGN KEY (adjusts_entry_id) REFERENCES journal_entries (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE journal_lines (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT           NOT NULL,
    entry_id   INT           NOT NULL,
    account_id INT           NOT NULL,
    debit      DECIMAL(12,2) NOT NULL DEFAULT 0,
    -- Una de las dos es 0. Lo vigila el dominio, no un CHECK (§5).
    credit     DECIMAL(12,2) NOT NULL DEFAULT 0,
    -- En las líneas de IVA, para el D-104 (RN-65).
    tax_rate   DECIMAL(5,2)  NULL,
    memo       VARCHAR(160)  NULL,
    INDEX idx_journal_lines_entry (entry_id),
    INDEX idx_journal_lines_account (company_id, account_id),
    CONSTRAINT fk_jl_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_jl_entry   FOREIGN KEY (entry_id)   REFERENCES journal_entries (id),
    CONSTRAINT fk_jl_account FOREIGN KEY (account_id) REFERENCES accounts (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- El costo se congela al vender (RN-63). NULL en las ventas anteriores a F11:
-- esas no entran al libro (RN-60).
ALTER TABLE sale_details
    ADD COLUMN unit_cost DECIMAL(12,2) NULL;
```

La fecha de inicio, la plantilla elegida y cuándo se activó van en el JSON de
`settings`, sección `accounting`, como el resto de la configuración de la
compañía.

### 13.3 Dominio y aplicación

`domain/ledger.py`, puro. `JournalEntry` no se puede construir desbalanceado:
el constructor suma y lanza `EntryNotBalanced` (RN-58). Las funciones que
convierten evento en asiento reciben el evento, sus líneas y el mapeo, y
devuelven el asiento; no saben de base ni de reloj.

El caso que fija todo lo demás es el invariante de siempre. Venta 3 × 1 450 al
13 %, en efectivo, con costo unitario ₡900:

```
subtotal 4 350,00 · IVA 565,50 · total 4 915,50

D  Caja                        4 915,50
   C  Ventas 13 %                          4 350,00
   C  IVA por pagar 13 %                     565,50   (tax_rate 13)
D  Costo de ventas             2 700,00
   C  Inventario                           2 700,00
                               ────────    ────────
                               7 615,50    7 615,50
```

| Función | Qué asienta | Casos |
|---|---|---|
| `post_sale(sale, lines, mapping)` | caja / tarjetas por cobrar / clientes según `payment_method`; ventas por tarifa; IVA por tarifa; costo e inventario | el de arriba; tarjeta; tarifas mezcladas 13 + 2 + 0; línea sin costo (NULL → sin par costo/inventario); método desconocido → por clasificar |
| `post_return(ret, lines, mapping)` | el inverso, con la tarifa de la línea (RN-12) | devolución parcial del ejemplo de §6.3 |
| `post_cash_close(session, expected, counted, mapping)` | la diferencia a sobrante o faltante | 53 000 contra 53 277,00 → faltante 277,00; cuadrado → sin asiento |
| `post_cash_movement(mov, mapping)` | entrada o salida contra por clasificar, salvo que sea de un abono | entrada 5 000; salida ligada a `supplier_payments` → no duplica |
| `post_purchase(entry, lines, mapping)` | inventario; IVA crédito por tarifa; proveedores (crédito) o caja (contado) | compra a crédito 100 000 + 13 000; contado |
| `post_supplier_payment(pay, mapping)` | proveedores contra caja o bancos | abono 50 000 en efectivo |
| `trial_balance(lines)`, `income_statement`, `balance_sheet` | sumas por cuenta y por tipo | un periodo con los asientos de arriba: activo = pasivo + patrimonio + resultado |
| `vat_draft(sales_by_rate, purchases_by_rate)` | débito − crédito por tarifa | 565,50 − 13 000 → saldo a favor |
| `assert_open(period, date)` | RN-61 | fecha en cerrado → `PeriodClosed` |

Puertos: `Ledger` (`post(entry)`), `AccountRepository`, `MappingRepository`,
`PeriodRepository`, `EntryNumberSequence`. El puerto `Ledger` es lo que permite
que `RegisterSale`, `RegisterReturn`, `CloseCashSession`, `RegisterCashMovement`,
`RegisterPurchase` y `PaySupplier` **no sepan si contabilidad está activa**:
con el módulo apagado el adaptador es nulo y las pruebas de caracterización
siguen dando las mismas cifras; con el módulo activo, el adaptador escribe en
la misma sesión de SQLAlchemy y el `commit` es uno solo.

Casos de uso nuevos: `ActivateAccounting` (siembra catálogo y mapeo, crea el
periodo de la fecha de inicio, escribe la apertura), `RecordManualEntry`,
`Reclassify` (mueve un saldo de por clasificar con un asiento de ajuste),
`ClosePeriod` (exige el anterior cerrado; deja el siguiente abierto; bitácora).

### 13.4 API y pantallas

```
POST /accounting/activate     admin · {template, start_date, opening_lines}
GET  /accounting/accounts · POST · PUT /{id}       admin escribe
GET  /accounting/mappings · PUT                    admin
GET  /accounting/entries?year=&month=&kind=        cualquiera con el módulo
POST /accounting/entries                           admin · manual o de ajuste
GET  /accounting/entries/{id}
GET  /accounting/periods · POST /{y}/{m}/close     admin, con confirmación
GET  /accounting/reports/{journal|ledger|trial-balance|income|balance}
                                                   ?year=&month=[&format=csv]
GET  /accounting/vat?year=&month=                  el borrador del D-104
```

Pantallas: `/contabilidad` (el periodo abierto, el saldo de por clasificar en
rojo si no es cero, los últimos asientos), `/contabilidad/cuentas`,
`/contabilidad/mapeo`, `/contabilidad/asientos` con el detalle y el manual,
`/contabilidad/periodos` con el cierre, `/contabilidad/reportes` con los cinco
y su CSV, `/contabilidad/iva`.

### 13.5 Códigos de error

`accounting_not_active`, `entry_not_balanced`, `period_closed`,
`period_not_closeable` (el anterior sigue abierto), `account_in_use`,
`account_is_system`, `invalid_opening_balance`.

### 13.6 Decisiones

| Tema | Qué se decidió | Por qué | Estado |
|---|---|---|---|
| Cuándo se asienta | En la misma transacción, con «por clasificar» | §13.1 | tomada |
| Desde cuándo | Fecha de inicio y apertura; nada hacia atrás | RN-60 | tomada |
| Periodos | Mensuales; cerrado no se reabre | RN-61 | tomada |
| Tarjetas | Bruto a tarjetas por cobrar; retención y comisión al liquidar | El número adivinado no coincide con el banco | tomada |
| Exportación | CSV | Sin dependencias; todo lo importa | tomada |
| **Rol contador** | Hoy solo el administrador entra a contabilidad y compras. Un contador externo (RN-3 ya lo menciona) necesitaría leer libros y escribir asientos sin tocar catálogo ni usuarios: un rol nuevo, el cuarto | Es una decisión de producto —cuántos roles se venden— y toca `user_companies.rol`, `requireAdmin` y el panel | **pendiente** |

### 13.7 Costes medidos antes de empezar

- `test_esquema.py`: cinco tablas y un `ALTER`.
- `test_aislamiento.py`: unas doce rutas.
- `test_error_codes.py`: siete códigos.
- `test_ports.py`: cinco puertos, y `Ledger` entra en la firma de seis casos de
  uso existentes.
- `company_dump.py`: las cinco tablas **viajan**.
- `test_characterization.py`: `RegisterSale` llama al `Ledger`; con el
  adaptador nulo las cifras no cambian, y esa es la prueba de que el enganche
  no toca el dinero.
- `sales.payment_method` es `VARCHAR(50)` libre: antes de mapear hay que
  cerrarlo a un conjunto de valores (T-1104).
- Cobertura: `domain/ledger.py` es el módulo de dominio más grande hasta ahora.
- El simulado: doce endpoints y un libro en el seed.
- Catálogo `accounting.json`, declarado.

### 13.8 Datos de referencia

Plantilla «comercio» que siembra `ActivateAccounting`. Es una plantilla de
trabajo, no una norma: el contador de cada compañía la ajusta, y se **revisa
con un contador antes de sembrarla** en producción.

| Código | Cuenta | Tipo | Sistema |
|---|---|---|---|
| 1.1.01 | Caja | asset | sí |
| 1.1.02 | Bancos | asset | sí |
| 1.1.03 | Tarjetas por cobrar | asset | sí |
| 1.1.04 | Clientes | asset | sí |
| 1.1.05 | IVA crédito fiscal | asset | sí |
| 1.1.06 | Retenciones a favor | asset | no |
| 1.2.01 | Inventario | asset | sí |
| 1.9.99 | Por clasificar | asset | sí |
| 2.1.01 | Proveedores | liability | sí |
| 2.1.02 | IVA por pagar | liability | sí |
| 2.1.03 | Retenciones de renta por pagar | liability | sí |
| 2.1.04 | CCSS por pagar | liability | sí |
| 2.1.05 | Salarios por pagar | liability | sí |
| 2.1.06 | Otras deducciones por pagar | liability | sí |
| 3.1.01 | Capital | equity | sí |
| 3.2.01 | Resultados acumulados | equity | sí |
| 4.1.01 … 4.1.05 | Ventas 13 %, 4 %, 2 %, 1 %, 0 % y exentas | income | sí |
| 4.2.01 | Devoluciones sobre ventas | income | sí |
| 4.9.01 | Sobrantes de caja | income | sí |
| 5.1.01 | Costo de ventas | cost | sí |
| 6.1.01 | Salarios | expense | sí |
| 6.1.02 | Cargas sociales patronales | expense | sí |
| 6.1.03 | Aguinaldo | expense | sí |
| 6.2.01 | Comisiones de tarjetas | expense | no |
| 6.9.01 | Faltantes de caja | expense | sí |
| 6.9.02 | Gastos generales | expense | no |

Mapeo por omisión: `sale` → `cash` 1.1.01, `cards_receivable` 1.1.03,
`receivable` 1.1.04, `sales_{tarifa}` 4.1.0n, `vat_payable` 2.1.02, `cogs`
5.1.01, `inventory` 1.2.01; `return` → los mismos más `sales_returns` 4.2.01;
`cash_close` → `cash_over` 4.9.01, `cash_short` 6.9.01; `purchase` →
`inventory`, `vat_credit` 1.1.05, `payables` 2.1.01; `supplier_payment` →
`payables`, `cash`, `bank` 1.1.02; `payroll` → 6.1.01, 6.1.02, 2.1.03, 2.1.04,
2.1.05, 2.1.06. Todo papel sin fila cae en 1.9.99.

---

## 14. Planilla (F12)

### 14.1 Lo que se congela y lo que se parametriza

La corrida guarda **cada rubro con su base, su tasa y su monto**
(`payroll_run_items`). Esa tabla **es** el congelamiento de RN-66: la boleta se
reimprime leyéndola, nunca recalculando. Cambiar una tasa es insertar una fila
con `valid_from` en `payroll_rates`; las corridas ya pagadas no la ven, y las
que vengan la toman por fecha de corte.

Las tasas son **globales por país**, no por compañía: son las mismas para
todos los patronos, las siembra la plataforma y las actualiza soporte desde
el panel para todas las compañías a la vez. Lo único que varía por compañía
—la prima de riesgos del trabajo del INS, que depende de la actividad, y el
aporte a la asociación solidarista— vive en el contrato o en la compañía, no
en la tabla global. No llevan `company_id`, como `cabys_cache`, y hay que
declararlas como excepción en `test_tenancy.py`.

Las fórmulas del dominio **no conocen ningún porcentaje**: reciben un
`RateSet` resuelto a una fecha y lo aplican. Las pruebas usan un juego de tasas
inventado; así prueban la aritmética y no una cifra que vence.

Decisiones que definen el alcance:

- **Empleado ≠ usuario** (RN-72). `employees.user_id` es opcional.
- **Renta con proyección mensual**: en una corrida quincenal el salario se
  proyecta al mes, se calcula la retención mensual por tramos y se aplica la
  mitad. Es la práctica del país y lo que la boleta tiene que mostrar.
- **La quincena es la mitad del salario mensual**, sin importar si el mes tiene
  28 o 31 días. Es lo que hacen los patronos y lo que el empleado espera; el
  cálculo por día queda para las liquidaciones y las incapacidades.
- **Incapacidades**: quién paga qué y desde qué día son **parámetros**
  (`payroll_rates` con conceptos `sick_leave_employer_days`,
  `sick_leave_employer_rate`…), porque cambian y difieren entre CCSS e INS.
- **El aguinaldo es una corrida** de tipo `aguinaldo`: suma lo devengado de las
  corridas pagadas del periodo y lo divide entre doce (RN-69); no lleva rubros
  de CCSS ni renta, y la prueba lo comprueba explícitamente.
- **La liquidación es una corrida** de tipo `settlement`, que nace al dar de
  baja: sus rubros son preaviso, cesantía, vacaciones y aguinaldo
  proporcionales, según la causa (RN-71).
- **Archivo bancario de pago**: fuera. La corrida pagada muestra la lista de
  IBAN y montos para copiar; el formato de cada banco es una tarea aparte
  cuando haya un cliente que lo pida.

### 14.2 Modelo de datos

```sql
-- 011-planilla.sql
-- Globales, por país: sin company_id (como cabys_cache). Excepción en test_tenancy.
CREATE TABLE payroll_rates (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    country     CHAR(2)      NOT NULL,      -- 'CR'
    -- 'sem', 'ivm', 'banco_popular', 'asignaciones_familiares', 'imas', 'ina',
    -- 'fcl', 'rop', 'sick_leave_employer_rate', …
    concept     VARCHAR(40)  NOT NULL,
    payer       VARCHAR(8)   NOT NULL,      -- 'employee' | 'employer' | 'rule'
    -- 0.0550 = 5,50 %; o el número de días, según el concepto.
    rate        DECIMAL(9,4) NOT NULL,
    valid_from  DATE         NOT NULL,
    valid_to    DATE         NULL,
    source      VARCHAR(255) NOT NULL,      -- la norma o la URL
    verified_at DATE         NOT NULL,      -- cuándo alguien lo comprobó
    UNIQUE KEY uq_payroll_rates (country, concept, payer, valid_from)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE income_tax_brackets (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    country     CHAR(2)       NOT NULL,
    valid_from  DATE          NOT NULL,
    valid_to    DATE          NULL,
    lower_bound DECIMAL(12,2) NOT NULL,
    upper_bound DECIMAL(12,2) NULL,        -- NULL: el último tramo
    rate        DECIMAL(5,4)  NOT NULL,
    source      VARCHAR(255)  NOT NULL,
    verified_at DATE          NOT NULL,
    UNIQUE KEY uq_income_tax_brackets (country, valid_from, lower_bound)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE income_tax_credits (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    country     CHAR(2)       NOT NULL,
    concept     VARCHAR(20)   NOT NULL,     -- 'child' | 'spouse'
    valid_from  DATE          NOT NULL,
    valid_to    DATE          NULL,
    amount      DECIMAL(12,2) NOT NULL,     -- mensual
    source      VARCHAR(255)  NOT NULL,
    verified_at DATE          NOT NULL,
    UNIQUE KEY uq_income_tax_credits (country, concept, valid_from)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE severance_table (              -- art. 29: días por año de antigüedad
    id          INT AUTO_INCREMENT PRIMARY KEY,
    country     CHAR(2)      NOT NULL,
    valid_from  DATE         NOT NULL,
    years_from  DECIMAL(4,2) NOT NULL,      -- 0.25 = tres meses
    years_to    DECIMAL(4,2) NULL,
    days        DECIMAL(5,2) NOT NULL,
    source      VARCHAR(255) NOT NULL,
    UNIQUE KEY uq_severance_table (country, valid_from, years_from)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- De acá en adelante, todo es de la compañía.
CREATE TABLE employees (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    company_id          INT          NOT NULL,
    user_id             INT          NULL,               -- RN-72: opcional
    identification_type CHAR(2)      NOT NULL,
    identification      VARCHAR(30)  NOT NULL,
    name                VARCHAR(160) NOT NULL,
    insured_number      VARCHAR(20)  NULL,               -- número de asegurado CCSS
    iban                VARCHAR(34)  NULL,
    position            VARCHAR(80)  NULL,
    hired_on            DATE         NOT NULL,
    terminated_on       DATE         NULL,
    -- 'resignation' | 'dismissal_with_cause' | 'dismissal_without_cause' |
    -- 'mutual' | 'end_of_contract'
    termination_cause   VARCHAR(30)  NULL,
    dependent_children  TINYINT      NOT NULL DEFAULT 0, -- crédito fiscal
    spouse_credit       TINYINT(1)   NOT NULL DEFAULT 0,
    is_active           TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_employees_identification (company_id, identification),
    CONSTRAINT fk_employees_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_employees_user    FOREIGN KEY (user_id)    REFERENCES users (id_user)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE employment_contracts (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    company_id       INT           NOT NULL,
    employee_id      INT           NOT NULL,
    valid_from       DATE          NOT NULL,
    valid_to         DATE          NULL,      -- un aumento lo cierra y abre otro
    base_salary      DECIMAL(12,2) NOT NULL,
    pay_frequency    VARCHAR(10)   NOT NULL,   -- 'weekly'|'biweekly'|'monthly'
    schedule         VARCHAR(10)   NOT NULL,   -- 'day' | 'mixed' | 'night'
    salary_kind      VARCHAR(10)   NOT NULL,   -- 'monthly' | 'hourly'
    solidarista_rate DECIMAL(5,4)  NULL,       -- aporte obrero, si hay
    rt_rate          DECIMAL(5,4)  NULL,       -- prima de RT de la compañía
    INDEX idx_employment_contracts_employee (employee_id, valid_from),
    CONSTRAINT fk_ec_company  FOREIGN KEY (company_id)  REFERENCES companies (id),
    CONSTRAINT fk_ec_employee FOREIGN KEY (employee_id) REFERENCES employees (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE payroll_runs (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    company_id       INT         NOT NULL,
    -- 'regular' | 'aguinaldo' | 'settlement' | 'adjustment'
    kind             VARCHAR(12) NOT NULL,
    period_from      DATE        NOT NULL,
    period_to        DATE        NOT NULL,
    pay_date         DATE        NOT NULL,
    -- 'draft' | 'approved' | 'paid' (RN-68)
    status           VARCHAR(10) NOT NULL DEFAULT 'draft',
    adjusts_run_id   INT         NULL,
    journal_entry_id INT         NULL,      -- RN-75, si hay contabilidad
    created_by       INT         NOT NULL,
    created_at       DATETIME    NOT NULL,
    approved_by      INT         NULL,
    approved_at      DATETIME    NULL,
    paid_by          INT         NULL,
    paid_at          DATETIME    NULL,
    INDEX idx_payroll_runs_period (company_id, period_from, kind),
    CONSTRAINT fk_pr_company FOREIGN KEY (company_id)     REFERENCES companies (id),
    CONSTRAINT fk_pr_adjusts FOREIGN KEY (adjusts_run_id) REFERENCES payroll_runs (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE payroll_run_lines (               -- un empleado en una corrida
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    company_id          INT           NOT NULL,
    run_id              INT           NOT NULL,
    employee_id         INT           NOT NULL,
    contract_id         INT           NOT NULL,
    gross               DECIMAL(12,2) NOT NULL,
    employee_deductions DECIMAL(12,2) NOT NULL,
    income_tax          DECIMAL(12,2) NOT NULL,
    net                 DECIMAL(12,2) NOT NULL,
    employer_charges    DECIMAL(12,2) NOT NULL,
    UNIQUE KEY uq_payroll_run_lines (run_id, employee_id),
    CONSTRAINT fk_prl_company  FOREIGN KEY (company_id)  REFERENCES companies (id),
    CONSTRAINT fk_prl_run      FOREIGN KEY (run_id)      REFERENCES payroll_runs (id),
    CONSTRAINT fk_prl_employee FOREIGN KEY (employee_id) REFERENCES employees (id),
    CONSTRAINT fk_prl_contract FOREIGN KEY (contract_id) REFERENCES employment_contracts (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

-- Los rubros SON las tasas congeladas (RN-66). La boleta se reimprime de acá.
CREATE TABLE payroll_run_items (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    company_id INT           NOT NULL,
    line_id    INT           NOT NULL,
    -- 'base', 'overtime', 'holiday', 'sem', 'ivm', 'income_tax',
    -- 'solidarista', 'garnishment', …
    concept    VARCHAR(40)   NOT NULL,
    payer      VARCHAR(8)    NOT NULL,    -- 'earning' | 'employee' | 'employer'
    base       DECIMAL(12,2) NOT NULL,
    -- NULL en los montos fijos (una deducción de ₡20 000).
    rate       DECIMAL(9,4)  NULL,
    amount     DECIMAL(12,2) NOT NULL,
    INDEX idx_payroll_run_items_line (line_id),
    CONSTRAINT fk_pri_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_pri_line    FOREIGN KEY (line_id)    REFERENCES payroll_run_lines (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE payroll_novelties (               -- lo que cambia respecto del contrato
    id          INT AUTO_INCREMENT PRIMARY KEY,
    company_id  INT           NOT NULL,
    run_id      INT           NOT NULL,
    employee_id INT           NOT NULL,
    -- 'overtime' | 'holiday' | 'sick_leave' | 'vacation' | 'deduction' | 'bonus'
    kind        VARCHAR(20)   NOT NULL,
    quantity    DECIMAL(8,2)  NOT NULL DEFAULT 0,   -- horas o días
    amount      DECIMAL(12,2) NULL,                 -- deducciones y bonos fijos
    memo        VARCHAR(160)  NULL,
    INDEX idx_payroll_novelties_run (run_id, employee_id),
    CONSTRAINT fk_pn_company  FOREIGN KEY (company_id)  REFERENCES companies (id),
    CONSTRAINT fk_pn_run      FOREIGN KEY (run_id)      REFERENCES payroll_runs (id),
    CONSTRAINT fk_pn_employee FOREIGN KEY (employee_id) REFERENCES employees (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE vacation_movements (              -- el saldo es una suma (RN-70)
    id          INT AUTO_INCREMENT PRIMARY KEY,
    company_id  INT          NOT NULL,
    employee_id INT          NOT NULL,
    kind        VARCHAR(10)  NOT NULL,     -- 'accrual' | 'taken' | 'paid'
    days        DECIMAL(6,2) NOT NULL,
    on_date     DATE         NOT NULL,
    run_id      INT          NULL,
    INDEX idx_vacation_movements_employee (employee_id, on_date),
    CONSTRAINT fk_vm_company  FOREIGN KEY (company_id)  REFERENCES companies (id),
    CONSTRAINT fk_vm_employee FOREIGN KEY (employee_id) REFERENCES employees (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
```

### 14.3 Dominio y aplicación

`domain/payroll.py`, puro. Todo recibe el `RateSet` resuelto a la fecha de
corte; `rates_at(rates, date)` es la única función que mira fechas, y lanza
`RatesMissing` si a esa fecha falta un concepto.

| Función | Regla | Casos (con tasas inventadas) |
|---|---|---|
| `gross_pay(contract, period, novelties)` | base según periodicidad; horas extra a tiempo y medio; feriado de pago obligatorio doble | mensual 600 000 quincenal → 300 000; 4 h extra sobre 240 h/mes; un feriado trabajado |
| `employee_deductions(gross, rates)` | cada rubro obrero: base × tasa, redondeo por rubro | tres rubros; la suma no se redondea dos veces |
| `employer_charges(gross, rates, contract)` | cada rubro patronal + RT del contrato | idem, con prima 1 % |
| `income_tax(monthly_gross, brackets, credits)` | tramos marginales, menos créditos, nunca negativo | bajo el piso → 0; en dos tramos; con dos hijos |
| `projected_monthly(gross, frequency)` | quincenal × 2, semanal × 52 ÷ 12 | los tres |
| `aguinaldo(earned)` | suma ÷ 12; sin cargas ni renta (RN-69) | doce meses iguales; siete meses; con horas extra |
| `vacation_accrual(days_worked)` | dos semanas por cincuenta (art. 153) | 350 días → 14; 25 días → 1 |
| `notice_days(seniority)` | art. 28 | 4 meses → 7 días; 8 meses → 15; 2 años → 30 |
| `severance_days(seniority, table)` | art. 29, topada | 1 año; 8 años; 12 años → tope de 8 |
| `settlement(cause, ...)` | RN-71 | renuncia: sin preaviso ni cesantía; despido sin causa: todo; con causa: proporcionales |
| `sick_leave_split(days, daily, rules)` | quién paga qué día | 2 días; 10 días |

Puertos: `RateTable`, `EmployeeRepository`, `PayrollRepository`,
`PayslipRenderer`, `CcssFileWriter`, y el `Ledger` de F11. Casos de uso:
`CreateRun`, `CalculateRun` (escribe líneas y rubros: el congelamiento),
`ApproveRun`, `PayRun` (fecha del servidor, bitácora, `Ledger.post` si hay
contabilidad), `AdjustRun`, `TerminateEmployee` (cierra el contrato y crea la
corrida de liquidación en borrador), `ExportCcssFile`, `IncomeTaxSummary`.

### 14.4 API y pantallas

```
GET  /payroll/employees · POST · PUT /{id} · POST /{id}/terminate      admin
GET  /payroll/contracts?employee= · POST                              admin
GET  /payroll/rates?on=                     lo vigente a una fecha, con su
                                            fuente y su verified_at
PUT  /support/payroll/rates                 soporte · inserta una fila con
                                            vigencia; nunca edita la vigente
GET  /payroll/runs · POST                   admin
POST /payroll/runs/{id}/novelties · /calculate · /approve · /pay · /adjust
GET  /payroll/runs/{id}                     líneas y rubros
GET  /payroll/runs/{id}/payslips/{employee} la boleta
GET  /payroll/vacations/{employee}          saldo y movimientos
GET  /payroll/exports/ccss?year=&month=     el archivo (RF-62)
GET  /payroll/exports/income-tax?year=&month=
```

Pantallas: `/planilla` (la corrida en curso y lo que vence: aguinaldo,
tasas viejas), `/planilla/empleados` con contrato y baja, `/planilla/corridas`
y `/planilla/corridas/{id}` con novedades, cálculo, aprobación, pago y
boletas, `/planilla/vacaciones`, `/planilla/tasas` (solo lectura, con fecha y
fuente). La boleta es la **cuarta plantilla de documento** —T-922 ya avisa que
el PDF del backend no se cuenta—, con el idioma del documento (RN-29).

### 14.5 Códigos de error

`rates_missing_for_date`, `contract_missing`, `employee_terminated`,
`run_not_editable`, `run_not_approved`, `run_already_paid`,
`settlement_requires_termination`, `novelty_outside_period`,
`vacation_balance_exceeded`.

### 14.6 Decisiones

| Tema | Qué se decidió | Por qué | Estado |
|---|---|---|---|
| Tasas | Globales por país, con vigencia; RT y solidarista en el contrato | Son las mismas para todos; lo que varía es poco y es de la compañía | tomada |
| Congelamiento | Los rubros de la corrida, con base y tasa | La boleta se reimprime de datos, no de código | tomada |
| Renta | Proyección mensual | Es la práctica y lo que la boleta muestra | tomada |
| Quincena | Mitad del mensual | Lo que hacen los patronos y espera el empleado | tomada |
| Aguinaldo y liquidación | Son corridas | Un solo modelo de estados, bitácora y asiento | tomada |
| Archivo bancario | Fuera | Un formato por banco; sin cliente que lo pida | tomada |
| Caja | La planilla no mueve la caja (RN-74) | Nómina y arqueo se descuadran juntos | tomada |
| ¿Quién edita las tasas? | Soporte, para todos; la compañía las ve | Una tasa mal escrita por un cliente es un reclamo laboral; una fila con vigencia de soporte es un dato con fuente | tomada |

### 14.7 Costes medidos antes de empezar

- `test_esquema.py`: once tablas.
- `test_tenancy.py`: cuatro tablas globales sin `TenantMixin`, declaradas como
  excepción explícita, como `cabys_cache`.
- `test_aislamiento.py`: unas quince rutas, y una bajo `/support`.
- `test_error_codes.py`: nueve códigos.
- `test_ports.py`: cinco puertos.
- `company_dump.py`: siete tablas **viajan**; las cuatro globales, **no**.
- Cobertura: `domain/payroll.py` supera a `ledger.py`; la tabla de casos es
  larga a propósito.
- El simulado: quince endpoints; dos empleados y un juego de tasas en el seed.
- Catálogo `payroll.json`, declarado. La boleta como cuarta plantilla, en los
  tres idiomas del documento.
- El asiento de planilla necesita el mapeo `payroll` de §13.8 sembrado desde
  F11, aunque no se use hasta acá.

### 14.8 Datos de referencia

**Nada de esta sección es una verdad del sistema: es lo que se siembra, con su
fuente y su fecha, y se comprueba contra la fuente oficial antes de
sembrarlo.** Las cifras concretas de porcentajes y tramos **no se escriben
acá**: cambian con decreto y se copiarían viejas. Se toman de `ccss.sa.cr`
(cuotas obrero-patronales), `hacienda.go.cr` (tramos y créditos del periodo
fiscal vigente) y el decreto de salarios mínimos del MTSS, el día que se
siembra, y esa fecha va en `verified_at`.

| Concepto | Pagador | Tabla | Fuente |
|---|---|---|---|
| SEM, IVM, Banco Popular | obrero y patrono | `payroll_rates` | CCSS. El IVM trae aumentos programados: varias filas con `valid_from` |
| Asignaciones Familiares, IMAS, INA, FCL, ROP, aporte patronal Banco Popular | patrono | `payroll_rates` | CCSS / Ley de Protección al Trabajador |
| Riesgos del trabajo | patrono, por actividad | `employment_contracts.rt_rate` | INS, la póliza de cada compañía |
| Total obrero ≈ 10,67 %, total patronal ≈ 26,67 % | — | — | **Aproximados, de referencia**: la prueba de la siembra suma los rubros y compara contra lo publicado ese día |
| Tramos del impuesto al salario y créditos por hijo y cónyuge | obrero | `income_tax_brackets`, `income_tax_credits` | Hacienda, decreto del periodo fiscal; se renuevan cada año |
| Preaviso | — | dominio (`notice_days`) | Código de Trabajo art. 28: 3–6 meses → 1 semana; 6–12 → 15 días; > 1 año → 1 mes |
| Cesantía | — | `severance_table` | art. 29: 3–6 meses → 7 días; 6–12 → 14; 1 año → 19,5; 2 → 20; 3 → 20,5; 4 → 21; 5 → 21,24; 6 → 21,5; 7 a 9 → 22; 10 → 21,5; 11 → 21; 12 → 20,5; 13 o más → 20; **tope de 8 años**. Verificar el texto vigente antes de sembrar |
| Aguinaldo | — | dominio | Ley 2412: 1 dic – 30 nov, ÷ 12, antes del 20 de diciembre, exento |
| Vacaciones | — | dominio | art. 153: dos semanas por cincuenta trabajadas |
| Horas extra y feriados | — | dominio | art. 139 (tiempo y medio) y arts. 148–149 (feriados de pago obligatorio, doble) |
| Incapacidad por enfermedad | patrono los primeros días, CCSS después | `payroll_rates` (`rule`) | CCSS: el porcentaje y desde qué día se toman del reglamento vigente el día de sembrar |
| Archivo de planilla para la CCSS | — | adaptador `CcssFileWriter` | La especificación del SICERE se lee **antes** de T-1211; el formato no se supone |
