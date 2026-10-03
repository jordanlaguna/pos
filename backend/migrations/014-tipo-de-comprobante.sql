-- ============================================================================
--  VentaSys · 014 — El tipo de comprobante de cada venta (F7, T-723, RN-85)
--
--  SE DECIDE AL VENDER
--
--  Una venta sale como factura (01) o como tiquete (04), y lo decide el
--  receptor: la factura exige uno identificado, así que el cliente de contado
--  solo puede recibir un tiquete. Hasta ahora no se guardaba y el documento
--  impreso lo deducía de la configuración de hoy: con la facturación activa,
--  toda venta salía «Factura electrónica», incluida la del cliente de contado.
--
--  NO CAMBIA DESPUÉS
--
--  El consecutivo va por tipo (RN-37) y la clave lleva el tipo adentro. Una
--  venta de antes de activar la facturación sigue siendo lo que fue.
--
--  NULO ES «SIN FACTURACIÓN ELECTRÓNICA»
--
--  Es lo que queda en todas las ventas anteriores a esta migración, y está
--  bien: ninguna se emitió ante Hacienda.
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

CALL ventasys_add_column('sales', 'document_type', 'CHAR(2) NULL');

DROP PROCEDURE ventasys_add_column;
