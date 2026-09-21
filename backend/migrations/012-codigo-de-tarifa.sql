-- ============================================================================
--  VentaSys · 012 — El código de tarifa del IVA (F7, T-715, RF-65, RN-76)
--
--  ONCE CÓDIGOS PARA NUEVE PORCENTAJES
--
--  El catálogo de Hacienda (nota 8.1 del anexo v4.4) no es una lista de tasas
--  sino de situaciones, y dos situaciones distintas pueden cobrar lo mismo:
--
--    01  0 %    art. 32 num 1 RLIVA — CON derecho a crédito pleno
--    11  0 %    no sujeto — SIN derecho a crédito
--
--  Los dos multiplican por cero y significan lo contrario. Por eso el código no
--  se puede deducir de `tax_rate` y necesita columna propia: el 4 % de un
--  servicio de salud (`04`) y el 4 % transitorio de una nota de crédito (`06`)
--  son el mismo número, y el 8 % **solo** existe como transitorio.
--
--  NACEN EN NULO Y ESO ES LO CIERTO
--
--  De los productos que ya están cargados no se sabe qué código les toca: se
--  sabe su porcentaje, y del porcentaje no se vuelve. Rellenar con `08` sería
--  declarar tarifa general sobre un catálogo que nadie revisó, y el día que se
--  emita el primer comprobante nadie sabría cuáles se eligieron y cuáles se
--  supusieron. NULL dice «falta clasificarlo», que es exactamente el estado.
--
--  El POS lo propone al editar el producto cuando la tarifa deja una sola
--  posibilidad —13 % es `08` y no hay otro— y **no lo propone en el 0 %**,
--  donde hay tres y la diferencia es el derecho a crédito del cliente.
--
--  EN LA LÍNEA DE LA VENTA SE CONGELA
--
--  Igual que `tax_rate` (RN-12) y por una razón más: sin el código guardado, la
--  nota de crédito de dentro de un año tendría que adivinar si aquel 0 % era un
--  `01` o un `11`.
--
--  Idempotente: se puede correr dos veces.
-- ============================================================================

SET NAMES utf8mb4;

-- --------------------------------------------------------------- productos

SET @existe := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'products'
      AND COLUMN_NAME = 'tax_code'
);
SET @sql := IF(
    @existe = 0,
    'ALTER TABLE products ADD COLUMN tax_code CHAR(2) NULL AFTER tax_rate',
    'SELECT "products.tax_code ya existe" AS aviso'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ------------------------------------------------------ líneas de la venta

SET @existe := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'sale_details'
      AND COLUMN_NAME = 'tax_code'
);
SET @sql := IF(
    @existe = 0,
    'ALTER TABLE sale_details ADD COLUMN tax_code CHAR(2) NULL AFTER tax_amount',
    'SELECT "sale_details.tax_code ya existe" AS aviso'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
