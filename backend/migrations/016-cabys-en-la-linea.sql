-- ============================================================================
--  VentaSys · 016 — El CABYS y la unidad, congelados en la línea (F7, T-731)
--
--  LA LÍNEA DICE CON QUÉ SE VENDIÓ
--
--  El comprobante impreso lleva, por línea, el código CABYS y la unidad de
--  medida (RN-86), y el XML también. Hasta acá vivían solo en `products`, y el
--  producto cambia: el dueño corrige un CABYS, o Hacienda actualiza el
--  catálogo. Leerlos del producto al reimprimir haría que una factura del mes
--  pasado dijera hoy otra cosa. Es la misma regla que congeló la tarifa en la
--  006 y el código de tarifa en la 012 (RN-12).
--
--  DOS COLUMNAS
--
--    cabys_code       los trece dígitos del catálogo de Hacienda
--    unit_of_measure  la unidad del comprobante: 'Unid', 'kg', 'Sp'…
--
--  NULO ES «ANTERIOR A ESTA MIGRACIÓN»
--
--  O un producto sin CABYS. No se rellenan con lo que diga hoy el producto:
--  sería justamente escribir en la venta un dato que no es el de entonces.
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

CALL ventasys_add_column('sale_details', 'cabys_code', 'CHAR(13) NULL');
CALL ventasys_add_column('sale_details', 'unit_of_measure', 'VARCHAR(15) NULL');

DROP PROCEDURE ventasys_add_column;
