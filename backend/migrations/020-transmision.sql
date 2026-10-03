-- ============================================================================
--  VentaSys · 020 — El recorrido del comprobante hasta Hacienda (F7, T-707 a T-712)
--
--  LO QUE LE FALTABA A `fe_documents`
--
--  La 018 dejó el comprobante numerado; esta le cuelga el recorrido: en qué
--  estado está, cuándo le toca el próximo paso, cuántas veces falló, por qué se
--  detuvo y dónde quedaron el XML firmado y la respuesta de Hacienda. Las
--  reglas están en `domain/fe_transmission.py`; acá solo hay columnas.
--
--    numerado ──> firmado ──> enviado ──> aceptado
--                    │            │
--                    │            └──> rechazado        (respuesta final)
--                    │
--                    └──> reintentando ──> detenido     (necesita a una persona)
--
--  Las filas que ya existen nacen `numbered`: son los comprobantes emitidos
--  antes de que hubiera transmisión. Se les pone próximo intento ya, para que
--  la cola los tome en cuanto arranque y lo numerado antes de hoy no quede sin
--  enviar en silencio.
--
--  LA BITÁCORA
--
--  `fe_document_events` guarda cada paso con su hora: lo que la pantalla de
--  facturas enseña como «por dónde va» (T-721). Solo se agrega.
--
--  El XML firmado y la respuesta NO están acá: van al almacén de objetos, y
--  estas columnas guardan solo su llave (plan §7.3).
--
--  Se corre una vez, como la 009: un segundo intento falla en la primera
--  columna repetida y no deja nada a medias.
-- ============================================================================

SET NAMES utf8mb4;

ALTER TABLE fe_documents
    ADD COLUMN status           VARCHAR(12)  NOT NULL DEFAULT 'numbered',  -- numbered | signed | sent | accepted | rejected | retrying | stopped
    ADD COLUMN failures         INT          NOT NULL DEFAULT 0,           -- fallas transitorias seguidas
    ADD COLUMN polls            INT          NOT NULL DEFAULT 0,           -- consultas del veredicto desde el envío
    ADD COLUMN first_failure_at DATETIME     NULL,
    ADD COLUMN last_attempt_at  DATETIME     NULL,
    ADD COLUMN next_attempt_at  DATETIME     NULL,                         -- nulo: ya no se mueve solo
    ADD COLUMN signed_at        DATETIME     NULL,
    ADD COLUMN sent_at          DATETIME     NULL,
    ADD COLUMN resolved_at      DATETIME     NULL,                         -- cuándo Hacienda aceptó o rechazó
    ADD COLUMN stop_reason      VARCHAR(40)  NULL,                         -- fe_transmission.STOP_*
    ADD COLUMN stop_detail      VARCHAR(500) NULL,                         -- lo que dijo Hacienda o la falla, crudo
    ADD COLUMN hacienda_status  VARCHAR(20)  NULL,                         -- el ind-estado tal cual
    ADD COLUMN xml_key          VARCHAR(200) NULL,                         -- llave del XML firmado en el almacén
    ADD COLUMN response_key     VARCHAR(200) NULL,                         -- llave de la respuesta de Hacienda
    -- La pregunta de la cola: «¿qué le toca ya a esta compañía?».
    ADD INDEX idx_fe_documents_queue (company_id, status, next_attempt_at);

-- Lo numerado antes de hoy entra a la cola: le toca ya.
UPDATE fe_documents
   SET next_attempt_at = NOW()
 WHERE status = 'numbered' AND next_attempt_at IS NULL;

CREATE TABLE IF NOT EXISTS fe_document_events (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    company_id  INT          NOT NULL,
    document_id INT          NOT NULL,
    at          DATETIME     NOT NULL,
    event       VARCHAR(20)  NOT NULL,     -- signed, sent, polled, accepted, rejected, deferred, stopped, resumed, xml_lost
    detail      VARCHAR(500) NULL,
    INDEX idx_fe_document_events_document (document_id, id),
    CONSTRAINT fk_fe_document_events_company  FOREIGN KEY (company_id)  REFERENCES companies (id),
    CONSTRAINT fk_fe_document_events_document FOREIGN KEY (document_id) REFERENCES fe_documents (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;
