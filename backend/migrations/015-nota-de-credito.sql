-- ============================================================================
--  VentaSys · 015 — La nota de crédito de una devolución (F7, T-725, RN-89)
--
--  UNA DEVOLUCIÓN DE UN COMPROBANTE ES UNA NOTA DE CRÉDITO
--
--  Devolver algo de una venta que salió como tiquete o factura tiene que pasar
--  por una nota de crédito que la referencie. Se guarda en la devolución misma
--  y no en una tabla aparte: la plata, el inventario y el asiento ya son los de
--  la devolución, y una segunda fila para lo mismo sería una segunda copia que
--  puede discrepar.
--
--  DOS COLUMNAS
--
--    document_type   '03' nota de crédito
--    reference_code  el motivo del catálogo de Hacienda: '06' devolución de
--                    mercancía, '01' anula
--
--  NULO ES «LA VENTA NO FUE COMPROBANTE»
--
--  Es lo que queda en todas las devoluciones anteriores a esta migración, y está
--  bien: ninguna de esas ventas se emitió, así que no hay qué referenciar.
--
--  Idempotente: se puede correr dos veces.
-- ============================================================================

SET NAMES utf8mb4;

DROP PROCEDURE IF EXISTS ventasys_add_column;
DELIMITER //
CREATE PROCEDURE ventasys_add_column(
    IN tabla VARCHAR(64), IN columna VARCHAR(64), IN definicion TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = tabla AND COLUMN_NAME = columna
    ) THEN
        SET @sql := CONCAT('ALTER TABLE ', tabla, ' ADD COLUMN ', columna, ' ', definicion);
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

CALL ventasys_add_column('returns', 'document_type', 'CHAR(2) NULL');
CALL ventasys_add_column('returns', 'reference_code', 'CHAR(2) NULL');

DROP PROCEDURE ventasys_add_column;
