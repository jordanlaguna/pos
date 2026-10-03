-- ============================================================================
--  VentaSys · 017 — Las notas por monto (F7, T-726, RF-77)
--
--  LA NOTA QUE NO MUEVE MERCADERÍA
--
--  La nota de débito le sube el monto a líneas de un comprobante y la nota de
--  crédito por monto se lo baja, sin que vuelva ni salga nada del inventario.
--  Hoy con un solo motivo, '02', corrige monto.
--
--  LA PLATA SE MUEVE EN EL MOMENTO
--
--  Decidido por el usuario el 2026-09-26: sin venta a crédito no hay saldo del
--  cliente donde dejar una nota. La ND se cobra al emitirla, con su medio de
--  pago; la NC sale de la gaveta, como una devolución. Las dos van al arqueo,
--  a las ventas netas y al asiento.
--
--  DOS TABLAS
--
--    sale_notes       la nota: la venta que corrige, el tipo, el motivo, por
--                     qué, cómo se cobró la ND y el desglose
--    sale_note_lines  a qué producto de la venta y por cuánto, con la tarifa,
--                     el código de tarifa, el CABYS y la unidad DE LA LÍNEA DE
--                     LA VENTA, copiados al emitir (RN-12, RN-86)
--
--  Los índices son los del modelo (`model_note.py`): el modelo y la migración
--  dicen lo mismo, o una instalación nueva y una migrada se comportan distinto.
--
--  Idempotente: se puede correr dos veces.
-- ============================================================================

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS sale_notes (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    company_id     INT           NOT NULL,
    sale_id        INT           NOT NULL,
    user_id        INT           NOT NULL,
    branch_id      INT           NOT NULL,
    terminal_id    INT           NOT NULL,
    created_at     DATETIME      NOT NULL,     -- la pone el servidor
    document_type  CHAR(2)       NOT NULL,     -- '02' ND, '03' NC
    reference_code CHAR(2)       NOT NULL,     -- el motivo de Hacienda
    reason         VARCHAR(255)  NOT NULL,
    payment_method VARCHAR(50)   NULL,         -- la ND; nulo en la NC
    subtotal       DECIMAL(10,2) NOT NULL,
    tax            DECIMAL(10,2) NOT NULL,
    total          DECIMAL(10,2) NOT NULL,
    INDEX ix_sale_notes_id (id),
    INDEX idx_sale_notes_sale (sale_id),
    INDEX idx_sale_notes_created (created_at),
    CONSTRAINT fk_sale_notes_company  FOREIGN KEY (company_id)  REFERENCES companies (id),
    CONSTRAINT fk_sale_notes_sale     FOREIGN KEY (sale_id)     REFERENCES sales (id),
    CONSTRAINT fk_sale_notes_user     FOREIGN KEY (user_id)     REFERENCES users (id_user),
    CONSTRAINT fk_sale_notes_branch   FOREIGN KEY (branch_id)   REFERENCES branches (id),
    CONSTRAINT fk_sale_notes_terminal FOREIGN KEY (terminal_id) REFERENCES terminals (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

CREATE TABLE IF NOT EXISTS sale_note_lines (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    company_id      INT           NOT NULL,
    note_id         INT           NOT NULL,
    product_id      INT           NOT NULL,
    subtotal        DECIMAL(10,2) NOT NULL,
    tax_rate        DECIMAL(7,6)  NOT NULL,
    tax_amount      DECIMAL(10,2) NOT NULL,
    tax_code        CHAR(2)       NULL,
    cabys_code      CHAR(13)      NULL,
    unit_of_measure VARCHAR(15)   NULL,
    INDEX ix_sale_note_lines_id (id),
    INDEX idx_sale_note_lines_note (note_id),
    CONSTRAINT fk_sale_note_lines_company FOREIGN KEY (company_id) REFERENCES companies (id),
    CONSTRAINT fk_sale_note_lines_note    FOREIGN KEY (note_id)    REFERENCES sale_notes (id),
    CONSTRAINT fk_sale_note_lines_product FOREIGN KEY (product_id) REFERENCES products (id_product)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
