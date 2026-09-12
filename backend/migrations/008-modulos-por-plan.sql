-- ============================================================================
--  VentaSys · 008 — Los módulos que incluye un plan (F10, T-1001)
--
--  Compras, contabilidad y planilla no son parte del POS: son módulos que un
--  plan incluye o no (spec §2 «Módulos», RN-49 a RN-51). Un abarrotes que solo
--  quiere cobrar no tiene por qué ver un libro mayor, y el producto tiene que
--  poder cobrarlos aparte.
--
--  NO ES UNA TABLA NUEVA, y es la decisión de fondo. `plans` ya dice qué deja
--  hacer el sistema —cuántas sucursales, cuántas cajas, cuánta gente— y ya
--  tiene una bandera de módulo desde la 002: `factura_electronica`. Un
--  interruptor por compañía, aparte del plan, serían dos sitios para la misma
--  verdad, y el día que discrepen nadie sabría cuál manda.
--
--  POR QUÉ EN INGLÉS, AL LADO DE COLUMNAS EN ESPAÑOL
--
--  `plans` trae `nombre`, `precio_mensual`, `max_sucursales`, `max_terminales`,
--  `max_usuarios` y `factura_electronica` de la migración 002. Se quedan así
--  (T-913, plan.md §3.9): el rename son 58 archivos y ~890 menciones, trece de
--  los diecisiete nombres son claves JSON publicadas, y `company_dump.py`
--  exporta por nombre de columna con un `FORMATO` que no se entera del cambio
--  —o sea que todo respaldo ya entregado a un cliente quedaría inservible en
--  silencio—. Las columnas NUEVAS sí van en inglés, porque esa excepción es de
--  las que ya existen y no una licencia para las que vienen.
--
--  POR OMISIÓN, APAGADOS. Los planes que ya existen no incluyen ningún módulo:
--  nadie los compró. Encenderlos es trabajo de soporte, desde el panel, y queda
--  en bitácora como cualquier cambio de plan (RF-7, RF-39).
--
--  CORRERLA
--     docker exec -i mysql_db_api sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" posdb' \
--         < backend/migrations/008-modulos-por-plan.sql
--
--  NO ES IDEMPOTENTE: `ADD COLUMN` sobre una columna que ya está falla. Correrla
--  dos veces da «Duplicate column name 'purchases'» y no cambia nada.
-- ============================================================================

SET NAMES utf8mb4;


-- ----------------------------------------------------------------------------
-- 1. Las tres banderas
--
--    TINYINT(1) NOT NULL DEFAULT 0, igual que `factura_electronica`, para que
--    el modelo —que las declara `Boolean` con `server_default=text("0")`— diga
--    exactamente lo mismo. Es lo que compara `tests/test_esquema.py`: una
--    instalación nueva arma el esquema con `create_all` y una vieja lo trae de
--    acá, y si difieren el mismo código corre sobre dos bases distintas.
-- ----------------------------------------------------------------------------

ALTER TABLE plans
    ADD COLUMN purchases  TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN accounting TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN payroll    TINYINT(1) NOT NULL DEFAULT 0;


-- ----------------------------------------------------------------------------
-- 2. Comprobación
--
--    Las tres columnas existen, son TINYINT(1), no admiten NULL y valen 0 por
--    omisión. Tiene que devolver TRES filas, todas con 'NO' y '0'.
-- ----------------------------------------------------------------------------

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'plans'
  AND COLUMN_NAME IN ('purchases', 'accounting', 'payroll')
ORDER BY COLUMN_NAME;
