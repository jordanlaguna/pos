-- ============================================================================
--  VentaSys · 006 — Impuesto por producto y CABYS (F5)
--
--  Hoy hay UNA tasa de impuesto para todo el negocio. Es incorrecto incluso sin
--  factura electrónica: un abarrotes vende canasta básica al 1 % mientras cobra
--  13 % en el resto, y un medicamento va al 2 %. Desde acá cada producto lleva
--  la suya, y cada línea de venta **congela** la que se le cobró.
--
--  Corresponde a task.md T-501, T-507 y T-509b; plan.md §6; spec.md RF-17 a
--  RF-21, RN-9 a RN-12.
--
--  CORRERLA
--     docker exec -i mysql_db_api sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" posdb' \
--         < backend/migrations/006-impuesto-por-producto.sql
--
--  NO ES IDEMPOTENTE: correrla dos veces falla en el primer ALTER. Falla, no
--  corrompe.
--
--  NADA DE LO YA COBRADO CAMBIA. Todas las columnas nuevas nacen en NULL, y
--  NULL significa «la tasa configurada», que es exactamente lo que se venía
--  aplicando. No hay relleno de datos, no hay que leer la configuración de cada
--  compañía desde SQL, y una venta de ayer se devuelve hoy por el mismo monto.
--
--  LOS NOMBRES VAN EN INGLÉS —`tax_rate`, `unit_of_measure`, `cabys_cache`—
--  aunque plan.md §6.2 los escribiera en español al diseñarlos. Es la regla del
--  proyecto y lo que ya hizo F4 con `sort_order` e `is_active`. Las columnas en
--  español de `companies`, `plans` y compañía quedan como la excepción
--  documentada que son (plan.md §3.9, T-913).
-- ============================================================================

SET NAMES utf8mb4;


-- ----------------------------------------------------------------------------
-- 1. La tarifa del producto (T-507, RN-9)
--
--    `tax_rate` en NULL significa «la tasa configurada del negocio». No se
--    rellena con la configurada de cada compañía a propósito, por dos razones:
--
--      * Habría que leer un campo JSON (`settings.data`) desde SQL para cada
--        compañía, que es frágil y depende de cuál de las dos formas de la
--        clave tenga guardada esa fila (`tax.rate` o el viejo `impuesto.tasa`).
--      * Con NULL, un negocio que mañana cambie su tasa se la cambia a todo el
--        catálogo que no tocó, que es lo que hoy pasa y lo que espera. Rellenar
--        congelaría 27 productos en el 13 % sin que nadie lo pidiera.
--
--    RN-9 dice que la tasa configurada es «el valor por omisión de un producto
--    nuevo»: eso es la ficha, que la propone al crear, no un relleno del pasado.
--
--    `DECIMAL(7,6)` porque una tasa vive entre 0 y 1 con seis decimales, que es
--    la precisión de `TaxRate` (`domain/tax.py`, PRECISION). Los montos son
--    DECIMAL(10,2) y una tasa NO es un monto: guardar 0,13 con dos decimales
--    perdería el 2,5 % y cualquier tarifa fina de Hacienda.
--
--    `cabys_code` son 13 dígitos. Se guarda como CHAR y no como número: tiene
--    ceros a la izquierda y no se hace aritmética con él.
--
--    `unit_of_measure` la pide Hacienda en cada línea del comprobante (F6/F7).
--    Nace en 'Unid', que es el código de «unidad» del catálogo, porque es lo que
--    vende un punto de venta salvo que alguien diga otra cosa.
-- ----------------------------------------------------------------------------

ALTER TABLE products
    ADD COLUMN cabys_code      CHAR(13)      NULL                      AFTER barcode,
    ADD COLUMN tax_rate        DECIMAL(7,6)  NULL                      AFTER cabys_code,
    ADD COLUMN unit_of_measure VARCHAR(15)   NOT NULL DEFAULT 'Unid'   AFTER tax_rate;

-- Buscar productos por su código CABYS es la consulta de la asignación en lote
-- (RF-20) y la de «qué falta por clasificar». Lleva la compañía adelante porque
-- toda consulta de negocio la lleva: sin ella el índice no se usa.
CREATE INDEX idx_products_cabys ON products (company_id, cabys_code);


-- ----------------------------------------------------------------------------
-- 2. La tarifa se congela en la línea (T-509b, RN-12)
--
--    NO basta con tenerla en `products`, y las dos razones son la misma regla
--    vista de dos lados:
--
--      1. La tarifa del producto cambia —Hacienda actualiza el catálogo, o el
--         dueño corrige el código—. Sin congelarla, devolver algo vendido el mes
--         pasado usaría la tarifa de hoy.
--      2. Con tarifas mezcladas, la del encabezado deja de servir. La
--         devolución la reconstruye como `tax / subtotal`, y eso funciona
--         mientras la venta lleve una sola tarifa. En cuanto se mezclan es un
--         PROMEDIO:
--
--             venta: medicamento ₡1 000 al 2 % + arroz ₡1 000 al 13 %
--                    subtotal ₡2 000 · impuesto ₡150 · promedio 7,5 %
--             devolver solo el medicamento → correcto  1 000 × 1,02 = ₡1 020
--                                            promedio  1 000 × 1,075 = ₡1 075
--
--         ₡55 de más, y ₡55 de menos si se devuelve el arroz. La caja no cuadra
--         y nadie sabe por qué.
--
--    NULL es «venta anterior a esta migración»: esas llevan una sola tarifa y
--    el cociente del encabezado la reconstruye exacta (`TaxRate.of_sale`).
--    Por eso la columna es nullable y no tiene DEFAULT: el nulo es información.
--
--    Se guarda también `tax_amount` y no solo la tasa. Es redundante —se puede
--    recalcular— y aun así se guarda: es lo que se cobró de verdad, incluido su
--    redondeo, y una factura tiene que poder reimprimirse igual dentro de cinco
--    años aunque cambie cómo se redondea.
-- ----------------------------------------------------------------------------

ALTER TABLE sale_details
    ADD COLUMN tax_rate   DECIMAL(7,6)   NULL AFTER subtotal,
    ADD COLUMN tax_amount DECIMAL(10,2)  NULL AFTER tax_rate;

ALTER TABLE return_details
    ADD COLUMN tax_rate   DECIMAL(7,6)   NULL AFTER subtotal,
    ADD COLUMN tax_amount DECIMAL(10,2)  NULL AFTER tax_rate;


-- ----------------------------------------------------------------------------
-- 3. La devolución necesita dónde guardar su desglose
--
--    `returns` guardaba SOLO `total`. Con una tarifa daba igual —el impuesto se
--    deducía— pero con tarifas mezcladas no hay de dónde deducirlo, así que una
--    devolución no tendría desglose que reimprimir ni con qué cuadrar la caja.
--    Esto no estaba en T-509b: apareció al medir la superficie de F5 el
--    2026-09-05, y sin ello la fase quedaba a medias.
--
--    NULL otra vez es «anterior a la migración»: ahí el desglose se deduce del
--    total y de la tasa reconstruida, que para esas es exacta.
-- ----------------------------------------------------------------------------

ALTER TABLE returns
    ADD COLUMN subtotal DECIMAL(10,2) NULL AFTER reason,
    ADD COLUMN tax      DECIMAL(10,2) NULL AFTER subtotal;


-- ----------------------------------------------------------------------------
-- 4. La caché del catálogo de Hacienda (T-501)
--
--    GLOBAL, no por compañía, y por eso NO lleva `company_id` ni hereda el
--    filtro de `tenancy.py`: el catálogo CABYS es del país, es el mismo para
--    todos los clientes y cachearlo por compañía sería guardar veinte copias de
--    la misma fila y pedirle veinte veces lo mismo a Hacienda.
--
--    Es la segunda tabla global del sistema, después de `plans`. Hay que
--    declararla como tal en `company_dump.py` (TABLAS_AJENAS) o el respaldo por
--    compañía se niega a correr: tiene un control que exige que toda tabla esté
--    clasificada.
--
--    Se llena con los códigos que se van usando, no con el catálogo entero: son
--    unos veinte mil y un POS usa unas decenas. Al asignarle un código a un
--    producto se copia acá, y por eso **facturar no depende de que Hacienda esté
--    arriba** (RNF-4).
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cabys_cache (
    code        CHAR(13)      NOT NULL,
    description VARCHAR(500)  NOT NULL,
    tax_rate    DECIMAL(7,6)  NOT NULL,
    updated_at  DATETIME      NOT NULL,
    PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ----------------------------------------------------------------------------
-- 5. Nueve índices que estaban escritos y nunca se aplicaron
--
--    No son de F5. Vienen de `migration.sql`, que el README describe como
--    «arreglos heredados, para una base anterior a F1» y que **nunca se corrió
--    contra esta base**: se comprobó por los nombres de los índices vivos
--    —`products` tiene `ix_products_barcode`, el nombre que genera SQLAlchemy,
--    y no el `idx_products_barcode` de aquel archivo—. Las tablas base las creó
--    `create_all` al arrancar y encima fueron las migraciones numeradas.
--
--    O sea que estos nueve estaban escritos, revisados y sin efecto. Se aplican
--    acá porque son los de las consultas que más se repiten y porque F5 es la
--    fase que abre estas tablas:
--
--      * `cash_sessions (user_id, status)` es LA consulta del arqueo —«el turno
--        abierto de este cajero»—, que corre en cada venta.
--      * `stock_entries (document_number)` sostiene la regla de la factura
--        duplicada: antes de aplicar una entrada se busca si ese número ya se
--        cargó y sigue aplicada.
--      * Los de `returns` y los detalles son «¿esta factura ya se devolvió?» y
--        el recorrido de líneas de una devolución o de una entrada.
--
--    Se declaran también en los modelos, que es lo que hace que una instalación
--    nueva los tenga (`tests/test_esquema.py` lo exige en los dos sentidos).
-- ----------------------------------------------------------------------------

CREATE INDEX idx_cash_sessions_user_status ON cash_sessions (user_id, status);
CREATE INDEX idx_cash_sessions_opened      ON cash_sessions (opened_at);
CREATE INDEX idx_cash_movements_session    ON cash_movements (session_id);

CREATE INDEX idx_returns_sale              ON returns (sale_id);
CREATE INDEX idx_returns_created           ON returns (created_at);
CREATE INDEX idx_return_details_return     ON return_details (return_id);

CREATE INDEX idx_stock_entries_created     ON stock_entries (created_at);
CREATE INDEX idx_stock_entries_document    ON stock_entries (document_number);
CREATE INDEX idx_stock_entry_details_entry ON stock_entry_details (entry_id);


-- ----------------------------------------------------------------------------
-- 6. Controles
-- ----------------------------------------------------------------------------

-- Esperado: cabys_code, tax_rate y unit_of_measure en products; tax_rate y
-- tax_amount en las dos tablas de detalle; subtotal y tax en returns.
SELECT 'columnas' AS control,
       TABLE_NAME,
       COLUMN_NAME,
       COLUMN_TYPE,
       IS_NULLABLE,
       COLUMN_DEFAULT
  FROM information_schema.COLUMNS
 WHERE TABLE_SCHEMA = DATABASE()
   AND (
        (TABLE_NAME = 'products'       AND COLUMN_NAME IN ('cabys_code','tax_rate','unit_of_measure'))
     OR (TABLE_NAME = 'sale_details'   AND COLUMN_NAME IN ('tax_rate','tax_amount'))
     OR (TABLE_NAME = 'return_details' AND COLUMN_NAME IN ('tax_rate','tax_amount'))
     OR (TABLE_NAME = 'returns'        AND COLUMN_NAME IN ('subtotal','tax'))
   )
 ORDER BY TABLE_NAME, COLUMN_NAME;

-- Esperado: 0 filas. Ninguna venta ya registrada cambia de impuesto con esta
-- migración; si alguna trajera tarifa, es que se corrió dos veces o que alguien
-- rellenó a mano.
SELECT 'lineas con tarifa' AS control, COUNT(*) AS filas
  FROM sale_details
 WHERE tax_rate IS NOT NULL;

-- Esperado: la tabla existe y está vacía.
SELECT 'cabys_cache' AS control, COUNT(*) AS filas FROM cabys_cache;
