# VentaSys — backend

API en FastAPI + SQLAlchemy 2 sobre MySQL 8. Es la fuente de verdad del
sistema: precios, existencias, turnos de caja y permisos se resuelven acá, y el
POS ([`../frontend/`](../frontend/)) nunca calcula plata por su cuenta.

Esta carpeta es **la aplicación completa y se levanta sola**. No hay nada que
ensamblar ni que copiar sobre otro repositorio.

```
backend/
├── app/                  la aplicación (57 módulos)
│   ├── database/         conexión y Base
│   ├── models/           tablas
│   ├── router/           endpoints
│   ├── schemas/          contratos de entrada y salida
│   ├── services/         lógica (crud_*)
│   └── utils/            JWT, hashing, dependencias de permisos
├── docker-compose.yml    MySQL + API + Adminer
├── Dockerfile
├── wait-for-db.sh
├── initdb/               dumps que se cargan al crear la base (vacío)
├── migration.sql         arreglos heredados, para una base anterior a F1
├── migrations/           migraciones numeradas de acá en adelante
├── requirements.txt
├── bootstrap.py          da de alta una compañía y su administrador
├── company_dump.py       respalda, borra y restaura UNA compañía
├── seed.py               datos de prueba vía API
└── .env.example
```

---

## Levantar

```bash
cp .env.example .env      # y editalo: contraseñas, SECRET_KEY, TZ
docker compose up -d --build
```

Comprobar:

```bash
curl http://localhost:8001/health          # {"status":"ok"}
curl -o /dev/null -w "%{http_code}\n" \
     http://localhost:8001/products/products_list   # 401 sin token
```

Ese `401` es la prueba de que los permisos están activos. Si responde `200`, los
routers no se están cargando.

| | |
|---|---|
| API | http://localhost:8001 · docs en `/docs` |
| Adminer | http://localhost:8080 (solo desde la propia máquina) |
| MySQL | 127.0.0.1:3306 |

Datos de prueba:

```bash
python seed.py --url http://localhost:8001 --ventas 35
```

> **El puerto es 8001, no 8000.** El compose publica `"8001:80"`.

### La primera compañía

Desde F2 la base es multiempresa y una base recién creada no tiene ninguna
compañía. Sin compañía no hay membresía, y sin membresía nadie entra —ni
siquiera para crear la primera—. Por eso el alta inicial no va por la API:

```bash
docker compose exec fastapi python bootstrap.py \
    --nombre "Mi negocio" --email admin@ventasys.cr --password admin123
```

Deja la compañía (afiliado 1, compañía 1), su sucursal `001`, su terminal
`00001`, su configuración vacía y la membresía de administrador. Es repetible: si
la compañía ya existe la reutiliza, y si la persona ya existe le agrega la
membresía —que es como se arma el caso del contador que atiende varios locales—.

Después, `seed.py` carga catálogo y ventas de ejemplo por HTTP.

### Base con datos previos

`create_all()` solo crea tablas que no existen; no modifica las que ya están. Si
la base viene de una instalación anterior hay que correr las migraciones, en
orden y después de un respaldo:

```bash
docker exec -i mysql_db_api sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" \
    --single-transaction --databases posdb' > respaldo.sql

# Anterior a F1: roles, DATETIME, ventas sin cliente…
docker exec -i mysql_db_api sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" posdb' \
    < migration.sql

# F2: multiempresa. Crea también la compañía 1 con todo lo que ya había adentro,
# así que después de esta NO hay que correr bootstrap.py.
docker exec -i mysql_db_api sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" posdb' \
    < migrations/002-multiempresa.sql

# La membresía se acepta en vez de imponerse. Las que ya existían quedan aceptadas.
docker exec -i mysql_db_api sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" posdb' \
    < migrations/003-invitaciones.sql
```

Ninguna es idempotente: MySQL 8 no tiene `ADD COLUMN IF NOT EXISTS`, así que
correrlas dos veces falla en el primer `ALTER`. Falla, no corrompe. Cada una
termina con consultas de control que dicen si quedó bien.

Sobre una base nueva no hacen falta: `create_all()` deja el mismo esquema
—comprobado columna por columna— y solo hay que correr `bootstrap.py`.

### Respaldar una sola compañía

Con base compartida, devolverle sus datos a un cliente ya no es un `mysqldump`:
hay que sacar sus filas de doce tablas en el orden que exigen las claves
foráneas. `company_dump.py` hace eso, y el camino de vuelta.

```bash
docker compose exec fastapi python company_dump.py exportar \
    --afiliado 2 --compania 1 --salida /tmp/cliente.json
docker compose cp fastapi:/tmp/cliente.json ./cliente.json

# Dar de baja. Pide el par escrito a mano: es lo único acá que destruye datos.
docker compose exec fastapi python company_dump.py borrar \
    --afiliado 2 --compania 1 --confirmar 2-1

# Y el camino de vuelta.
docker compose exec fastapi python company_dump.py importar --entrada /tmp/cliente.json
```

Conserva los identificadores: `auto_increment` de MySQL nunca reutiliza un
número, así que los de una compañía borrada quedan libres para siempre. El
precio es que restaurar **encima** de una compañía que todavía tiene filas está
prohibido, y el guion se niega antes de tocar nada.

`users` y `persons` no se borran con la compañía: son identidad global y pueden
estar compartidas con otra que sigue viva. Quedan sin membresía, que es lo
correcto.

---

## Pruebas

```bash
pip install -r requirements.txt -r requirements-dev.txt

docker compose -f docker-compose.test.yml up -d --build   # pila desechable, :8002
pytest
docker compose -f docker-compose.test.yml down -v         # borra la base de prueba
```

Son dos clases distintas:

| | |
|---|---|
| `tests/test_clock.py` | Código puro. Corre siempre, sin Docker. |
| `tests/test_characterization.py` | Contra FastAPI y MySQL de verdad. Sin la pila arriba se **omiten**, con el motivo en pantalla. |

La pila de pruebas es aparte a propósito: proyecto `ventasys-test`, puerto 8002
y la base en memoria sin volumen con nombre. Sin eso, cada corrida dejaría
productos, ventas y turnos inventados en la base de trabajo, y los reportes
dejarían de cuadrar sin que nadie entienda por qué. `down -v` la borra entera.

Las pruebas de caracterización fijan el comportamiento de hoy —los números de
`../.specify/progress.json`— antes de reorganizar el backend por capas. No
juzgan si está bien: dicen qué hace. Si una cambia al mover código, el refactor
rompió algo.

---

## Operación

```bash
docker compose logs -f fastapi        # ver logs
docker compose restart fastapi        # reiniciar solo la API
docker compose up -d --build          # reconstruir tras cambiar código
docker compose down                   # parar (conserva los datos)
docker compose down -v                # parar y BORRAR la base
```

Respaldo y restauración:

```bash
docker compose exec -T db mysqldump -u root -pCLAVE posdb > respaldo.sql
docker compose exec -T db mysql -u root -pCLAVE posdb < respaldo.sql
```

Para que el POS alcance la VM: `sudo ufw allow 8001/tcp`.

### El volumen no depende de la carpeta

El compose fija `name: ventasys` y llama al volumen `ventasys_db_data`. Sin eso,
Compose usa el nombre del directorio como prefijo, y mover o renombrar la
carpeta haría que MySQL arrancara contra un volumen vacío: parecería que se
perdió la base entera.

Si venís de un despliegue anterior levantado desde otra carpeta, los datos están
en `<carpeta>_db_data`. Con los dos stacks **abajo**, se copia así:

```bash
docker compose down                      # y también el stack viejo
docker volume create ventasys_db_data
docker run --rm -v <viejo>_db_data:/desde:ro -v ventasys_db_data:/hacia alpine \
  sh -c "cp -a /desde/. /hacia/"
docker compose up -d --build
```

Se copia el volumen en vez de restaurar un volcado porque **las cuentas de MySQL
viven dentro del propio volumen**: copiándolo, el usuario y la contraseña del
`.env` siguen sirviendo sin tocar nada. Con un volcado sobre una base nueva hay
que recrear también las cuentas.

Conviene comprobar antes de borrar el viejo:

```bash
docker run --rm -v <viejo>_db_data:/a:ro -v ventasys_db_data:/b:ro alpine \
  diff -r /a /b && echo "idénticos"
```

Si son datos de prueba, sale más barato volver a sembrar.

---

## Configuración (`.env`)

Todas las variables usan la forma `${VAR:?mensaje}`: si falta una, Compose se
niega a arrancar y dice cuál. Es a propósito. Con valores por defecto, un
despliegue al que se le olvidó el `.env` levanta igual —con la contraseña de
ejemplo y la clave de firma publicada— y nadie se entera.

| Variable | Para qué |
|---|---|
| `TZ` | **Crítica.** Ver más abajo. |
| `DB_NAME`, `DB_USER`, `DB_PASS`, `MYSQL_ROOT_PASSWORD` | Base de datos |
| `SECRET_KEY` | Firma de los JWT. `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Duración de la sesión (480 = 8 h) |
| `API_PORT` | Puerto publicado (8001) |
| `ALLOWED_ORIGINS` | Normalmente vacío: el POS habla servidor a servidor |

---

## Por qué el código es como es

Este backend viene de [`backend-python`](https://github.com/jordanlaguna/backend-python.git).
Durante la migración del POS aparecieron diez defectos, y al escribir las
pruebas apareció un undécimo. Varios solo se ven ejecutando el sistema, no
leyéndolo. Quedan acá porque explican decisiones que de otro modo parecen
arbitrarias.

### 1. Ventas fantasma — `services/crud_sale.py`

Hacía `db.commit()` de la cabecera **antes** de validar el stock, y su `except`
solo atrapaba `SQLAlchemyError`:

```python
db.add(db_sale)
db.commit()          # ← la venta ya quedó guardada
...
if db_product.stock < product.stock:
    raise HTTPException(...)   # ← sube sin rollback
```

`HTTPException` no es `SQLAlchemyError`, así que escapaba sin revertir nada.
Cada intento fallido por falta de existencias dejaba **una venta guardada sin
líneas y sin descontar inventario**, que además ensuciaba todos los reportes.

Ahora se valida todo primero y se escribe al final en una sola transacción, con
`SELECT ... FOR UPDATE` sobre los productos para que dos cajas no vendan la
misma última unidad.

### 2. El escáner nunca funcionó — `services/crud_product.py`

```python
def get_product_by_barcode(db, name):
    return db.query(Product).filter(Product.name == name).first()
```

Filtraba por **nombre**. Escanear un código no devolvía nada, nunca.

### 3. Las ventas perdían la hora — `models/model_sales.py`

`created_at` era `Column(Date)`: solo el día. Sin hora no se puede saber si una
venta ocurrió antes o después de abrir la caja, así que el arqueo por turno no
puede existir.

### 4. La API era pública — `utils/auth_dependency.py`

Se emitían JWT en el login pero **ningún endpoint los verificaba**. Se agregó
`get_current_user` (401 si el token falta, venció o apunta a un usuario borrado)
y `require_admin`, aplicados en todos los routers. Quedan públicos solo
`POST /auth/login` —que en F2 reemplazó a `POST /users/login`— y
`POST /persons/register`, que desde F2 crea una identidad sin ninguna compañía a
la que entrar: una puerta abierta a la nada, que es lo correcto mientras T-903 no
resuelva cómo se concede el primer administrador.

### 5. Ventas obligadas a tener cliente — `models/model_sales.py`

`client_id` era `NOT NULL`, y por eso el cliente WinForms mandaba `client_id = 1`
fijo: todas las ventas quedaban a nombre del mismo cliente.

### 6. El login se rompe en una máquina nueva — `utils/security.py`

`passlib[bcrypt]` sin versiones acotadas. passlib 1.7.4 es de 2020 y no conoce
las versiones nuevas de `bcrypt`: intenta leer `bcrypt.__about__.__version__`
—que ya no existe— y su rutina de detección le pasa un secreto de más de 72
bytes. bcrypt ≥ 4.1 dejó de truncar en silencio y lanza `ValueError`.

En una VM recién aprovisionada, `pip install -r requirements.txt` trae bcrypt 5.x
y **el registro y el login fallan con error 500** sin que nadie haya tocado el
código. Ahora se usa `bcrypt` directo; el formato del hash es el mismo
(`$2b$...`), así que las contraseñas guardadas siguen sirviendo.

### 7. La `SECRET_KEY` nunca se cargaba — `utils/jwt_handler.py`

`database.py` carga el `.env` con ruta explícita; `jwt_handler.py` hacía
`load_dotenv()` a secas, que lo busca en el directorio desde el que se lanza
uvicorn. No lo encontraba y `SECRET_KEY` caía en el valor por defecto, que está
publicado en el repositorio.

Mientras nadie verificaba los tokens daba igual. Ahora que se verifican, esa
clave es lo único que separa a un extraño de una sesión de administrador. Se usa
la misma ruta explícita y, si la clave sigue siendo la de por defecto, el
servidor lo avisa al arrancar.

### 8. Contenedores en UTC — `docker-compose.yml`

Sin `TZ`, los contenedores corren en UTC mientras el host está en hora local.
Comprobado: `host 2026-08-15 20:01` contra `contenedor 2026-08-16 02:01`.

Con UTC−6, **toda venta después de las 18:00 quedaba registrada como del día
siguiente**: el arqueo del turno de noche se partía en dos y los reportes
diarios salían corridos seis horas. `TZ` es obligatoria en el `.env`.

### 9. La hora la ponía el cliente — `services/crud_sale.py`

La venta se guardaba con el `created_at` que mandaba el POS. El turno de caja se
delimita comparando contra `cash_sessions.opened_at`, que sella este backend:
bastaba un desfase de segundos entre los dos relojes para que una venta quedara
fechada **antes** de la apertura y desapareciera del arqueo, sin ningún error
visible. Reproducido con 0,2 s de desfase. Ahora la hora la pone el servidor.

### 10. Paquete con el nombre mal escrito — `services/`

`app/services/__inti__.py`, con la `t` y la `i` cambiadas, y `app/utils/` sin
`__init__.py`. Funcionaba de casualidad: Python 3 trata un directorio sin
`__init__.py` como paquete de espacio de nombres. Corregido al reorganizar el
repositorio.

### 11. Ventas guardadas en el futuro — `utils/clock.py`

> Esta lista numera los defectos **del backend**. En
> `../.specify/progress.json`, que lleva la cuenta de todo el proyecto, este es
> el 14.


Las columnas de fecha son `DATETIME`, sin fracción de segundo, y MySQL
**redondea** al guardar: `10:00:05.700` queda almacenado como `10:00:06`.
Python escribía con microsegundos, así que una venta podía quedar guardada
hasta medio segundo por delante del reloj.

El arqueo delimita las ventas del turno con `created_at <= ahora`, y una venta
con marca futura no entra en esa ventana: **desaparecía de su propio turno**
hasta que el reloj la alcanzara. Si además la caja se cerraba dentro de ese
medio segundo, la venta no aparecía en ningún turno y el faltante quedaba sin
explicación posible.

Ahora toda escritura de fecha pasa por `clock.now()`, que trunca al segundo: lo
guardado nunca es posterior a lo ocurrido, que es la única relación que el
arqueo necesita. Lo encontraron las pruebas de caracterización al volverse
rápidas —con la suite lenta, el reloj siempre alcanzaba a la venta antes de que
alguien mirara—.

---

## Endpoints

| Prefijo | Qué |
|---|---|
| `/users` | login, alta, listado, `/me` con el rol |
| `/persons` | registro y datos personales |
| `/clients` | clientes |
| `/products`, `/categories` | catálogo |
| `/sales` | ventas, detalle de una venta, PDF |
| `/cash` | turnos de caja, movimientos, arqueo |
| `/returns` | devoluciones con reposición de existencias |
| `/reports` | resúmenes agregados en SQL (solo admin) |
| `/inventory` | entradas de mercadería y anulación |
| `/settings` | configuración del negocio (GET cualquiera, PUT solo admin) |

Detalle completo en `/docs` con el servidor arriba.

Los reportes se resuelven con SQL agregado, no trayendo filas a Python: con unos
meses de operación son decenas de miles de ventas.

---

## Verificado

Stack completo (`mysql:8` + FastAPI) contra MySQL real, no SQLite:

| | |
|---|---|
| Los tres relojes coinciden (host, fastapi, db) | ✅ |
| Compose se niega a arrancar sin `.env` | ✅ |
| `create_all()` deja el esquema correcto en base nueva | ✅ |
| Registro y login (bcrypt sin passlib) | ✅ |
| Petición sin token | ✅ 401 |
| Venta con `client_id: null`, stock 10 → 7 | ✅ |
| **Venta sin stock no deja factura fantasma** | ✅ 400, 0 filas nuevas |
| Devolución: 1450 × 1,13 = 1638,50 y stock 7 → 8 | ✅ |
| Arqueo 50 000 + 4 915,50 − 1 638,50 = 53 277,00 | ✅ |
| Cierre contando 53 000 → faltante −277,00 | ✅ |
| Cajero en rutas de admin | ✅ 403 |
| Configuración: GET con sesión, PUT solo admin | ✅ 403 al cajero |

Los números de referencia están en `../.specify/progress.json` → `invariantes_verificados`.
Si alguno deja de cuadrar, hay una regresión.

---

## Lo que viene

Este backend atiende a **un** negocio. El plan para volverlo multiempresa
—`company_id` en cada tabla, filtro automático en el ORM, panel de soporte,
impuesto por producto— está en [`../.specify/`](../.specify/).
