-- ============================================================================
--  VentaSys · 013 — La exoneración del cliente (F7, T-717, RF-67, RN-78)
--
--  SON PUNTOS DE TARIFA, NO UNA TARIFA
--
--  Lo que el documento de exoneración otorga es cuántos **puntos** se perdonan:
--  una línea al 13 % con nueve puntos exonerados paga 4 %. No existe ninguna
--  tarifa del 9 %, así que guardar «0.09» —o peor, «0.04»— sería guardar el
--  resultado en vez del dato, y el comprobante no cuadraría consigo mismo: el
--  monto exonerado sale de multiplicar los puntos por la base, y el impuesto
--  neto de restárselo al monto.
--
--  POR QUÉ SIETE COLUMNAS Y NO UNA TABLA
--
--  El XSD lleva **una** exoneración por línea de detalle: una segunda no
--  tendría dónde ir. Una tabla aparte solo haría falta para guardar historia,
--  y la historia de una exoneración ya está en los comprobantes emitidos, que
--  la llevan congelada.
--
--  NINGUNO SE DEDUCE DE OTRO
--
--  El tipo de documento (nota 10.1), la institución que lo emitió (nota 23), el
--  artículo y el inciso de la ley, la fecha y los puntos son seis datos
--  distintos que Hacienda cruza por separado. Con los tipos 04 y 11 además
--  comprueba contra su registro que el documento exista, esté vigente y que los
--  puntos no excedan los autorizados.
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

CALL ventasys_add_column('clients', 'exo_document_type', 'CHAR(2) NULL');
CALL ventasys_add_column('clients', 'exo_document_number', 'VARCHAR(40) NULL');
CALL ventasys_add_column('clients', 'exo_institution', 'CHAR(2) NULL');
CALL ventasys_add_column('clients', 'exo_institution_other', 'VARCHAR(160) NULL');
CALL ventasys_add_column('clients', 'exo_article', 'INT NULL');
CALL ventasys_add_column('clients', 'exo_subsection', 'INT NULL');
CALL ventasys_add_column('clients', 'exo_date', 'DATE NULL');
CALL ventasys_add_column('clients', 'exo_points', 'DECIMAL(4,2) NULL');

DROP PROCEDURE ventasys_add_column;
