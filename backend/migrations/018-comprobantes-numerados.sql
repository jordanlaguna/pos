-- ============================================================================
--  VentaSys · 018 — El comprobante numerado (F7, T-704, T-705)
--
--  EL NÚMERO Y LA CLAVE, AL VENDER
--
--  La clave de 50 dígitos se imprime y se entrega en el mostrador (RN-43), así
--  que se arma al vender, no al transmitir. Lleva el consecutivo de 20 —oficina,
--  caja, tipo y secuencia—, y la secuencia sale de `fe_sequences` (011), que ya
--  tenía las cinco dimensiones y hasta hoy nadie usaba.
--
--  UNA TABLA APARTE DE LA VENTA
--
--  Nacen comprobantes de tres sitios —la venta, la devolución con nota de
--  crédito y la nota por monto— y una misma venta puede tener más de uno en su
--  vida: un comprobante rechazado se corrige emitiendo otro con consecutivo
--  nuevo, no reescribiendo este. Por eso cuelga de su origen con
--  (source_type, source_id) y no es una columna de `sales`.
--
--  Aquí vendrán después el estado del recorrido (T-707) y el XML firmado.
--
--  LAS DOS REGLAS QUE CUIDA LA BASE
--
--    uq_fe_documents_clave        la clave no se repite dentro de la compañía
--    uq_fe_documents_consecutive  el consecutivo tampoco, dentro del ambiente:
--                                 uno de pruebas y uno de producción sí pueden
--                                 coincidir (RN-34)
--
--  Los índices son los del modelo (`model_fe.py`). Idempotente.
-- ============================================================================

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS fe_documents (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    company_id        INT         NOT NULL,
    source_type       VARCHAR(10) NOT NULL,     -- 'sale', 'return', 'note'
    source_id         INT         NOT NULL,
    document_type     CHAR(2)     NOT NULL,     -- 01 FE, 02 ND, 03 NC, 04 TE…
    environment       VARCHAR(12) NOT NULL,     -- 'sandbox' | 'production'
    branch_id         INT         NOT NULL,
    terminal_id       INT         NOT NULL,
    sequence_number   BIGINT      NOT NULL,
    consecutive       CHAR(20)    NOT NULL,
    clave             CHAR(50)    NOT NULL,
    situation         CHAR(1)     NOT NULL,     -- 1 normal, 2 contingencia, 3 sin internet
    economic_activity VARCHAR(10) NULL,         -- la declarada al emitir
    issued_at         DATETIME    NOT NULL,     -- la misma marca que su origen
    UNIQUE KEY uq_fe_documents_clave (company_id, clave),
    UNIQUE KEY uq_fe_documents_consecutive (company_id, environment, consecutive),
    INDEX idx_fe_documents_source (source_type, source_id),
    CONSTRAINT fk_fe_documents_company  FOREIGN KEY (company_id)  REFERENCES companies (id),
    CONSTRAINT fk_fe_documents_branch   FOREIGN KEY (branch_id)   REFERENCES branches (id),
    CONSTRAINT fk_fe_documents_terminal FOREIGN KEY (terminal_id) REFERENCES terminals (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
