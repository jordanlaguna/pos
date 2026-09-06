-- ============================================================================
--  VentaSys · 007 — Quitar el DEFAULT 1 de compañía, sucursal y terminal
--
--  Dieciocho columnas tienen `DEFAULT 1` en la base desplegada y ninguno en el
--  modelo. No es una decisión de diseño: es **la cicatriz del backfill de la
--  002**. `ALTER TABLE … ADD COLUMN company_id INT NOT NULL` sobre una tabla
--  que ya tiene filas necesita un valor para esas filas, así que se le puso 1
--  —la única compañía que existía entonces— y el DEFAULT se quedó en la
--  definición de la columna para siempre.
--
--  QUÉ ARREGLA
--
--  Que la misma base se comporte distinto según cómo se armó. En una
--  instalación **nueva** —esquema de `create_all`, que es también el de la
--  batería de pruebas— un INSERT que olvide la compañía revienta:
--
--      Field 'company_id' doesn't have a default value
--
--  En la base **migrada** de un cliente, el mismo INSERT entra callado y la
--  fila queda en la compañía 1. En la columna que sostiene todo el aislamiento
--  entre clientes, eso es la diferencia entre un error ruidoso y un dato ajeno
--  archivado en silencio. Hoy no hay ningún camino que lo haga —lo demuestra
--  que la batería corre contra el esquema sin defecto y pasa entera— pero el
--  día que aparezca uno, se quiere que falle donde se nota.
--
--  Corresponde a task.md T-919; el guardián que lo encontró es
--  `backend/tests/test_esquema.py`.
--
--  CORRERLA
--     docker exec -i mysql_db_api sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" posdb' \
--         < backend/migrations/007-sin-defecto-de-compania.sql
--
--  NO TOCA NI UNA FILA. `DROP DEFAULT` cambia la definición de la columna, no
--  su contenido: los valores que ya están se quedan como están, y todo INSERT
--  que hoy manda la compañía sigue funcionando igual. Es reversible con un
--  `ALTER … SET DEFAULT 1`.
--
--  ES IDEMPOTENTE, a diferencia de las anteriores: quitar un defecto que ya no
--  está no falla. Se puede correr dos veces.
-- ============================================================================

SET NAMES utf8mb4;


-- ----------------------------------------------------------------------------
-- 1. La compañía, en las doce tablas de negocio
-- ----------------------------------------------------------------------------

ALTER TABLE categories          ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE clients             ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE products            ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE sales               ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE sale_details        ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE returns             ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE return_details      ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE cash_sessions       ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE cash_movements      ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE stock_entries       ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE stock_entry_details ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE settings            ALTER COLUMN company_id DROP DEFAULT;


-- ----------------------------------------------------------------------------
-- 2. Sucursal y terminal (RN-14)
--
--    Mismo origen y mismo razonamiento: los agregó la 002 con `DEFAULT 1` para
--    poder rellenar lo que ya existía. Una venta sin terminal no es una venta
--    con la terminal 1: es una venta que no se sabe dónde se cobró, y el arqueo
--    de esa caja saldría cuadrado con plata que no pasó por ahí.
-- ----------------------------------------------------------------------------

ALTER TABLE sales         ALTER COLUMN branch_id   DROP DEFAULT;
ALTER TABLE sales         ALTER COLUMN terminal_id DROP DEFAULT;
ALTER TABLE returns       ALTER COLUMN branch_id   DROP DEFAULT;
ALTER TABLE returns       ALTER COLUMN terminal_id DROP DEFAULT;
ALTER TABLE cash_sessions ALTER COLUMN terminal_id DROP DEFAULT;
ALTER TABLE stock_entries ALTER COLUMN branch_id   DROP DEFAULT;


-- ----------------------------------------------------------------------------
-- 3. Comprobación
--
--    Tiene que devolver CERO filas. Cualquiera que salga es una columna que se
--    quedó con su defecto, y el guardián de `test_esquema.py` la va a señalar.
-- ----------------------------------------------------------------------------

SELECT TABLE_NAME, COLUMN_NAME, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND COLUMN_NAME IN ('company_id', 'branch_id', 'terminal_id')
  AND COLUMN_DEFAULT IS NOT NULL;
