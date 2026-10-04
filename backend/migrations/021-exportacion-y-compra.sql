-- ============================================================================
--  VentaSys · 021 — La factura de exportación y la de compra (F7, T-727 y T-728)
--
--  LO QUE LES FALTABA A LAS TABLAS
--
--  El armador del XML sabe los siete comprobantes desde T-720; lo que no había
--  era de dónde sacar los datos que la exportación y la compra piden y una
--  venta del país no tiene (plan §7.2, «De dónde nace cada comprobante»):
--
--    * `products.tariff_heading`      la partida arancelaria de cada mercancía,
--                                     doce dígitos exactos (XSD 4.4). NULL es
--                                     «no tiene», y solo importa al exportar.
--    * `clients.foreign_address`      las otras señas del cliente del extranjero
--                                     (identificación 05), que ocupan el lugar
--                                     de la ubicación del país en el receptor.
--    * `sale_details.tariff_heading`  la partida con que se exportó, congelada
--                                     como el CABYS: el producto puede cambiarla
--                                     después y el comprobante no.
--    * `stock_entries.document_type`  '08' cuando la compra a un no
--                                     contribuyente sale como factura
--                                     electrónica de compra; NULL si no.
--
--    * `fe_documents.unreachable_at`  la última vez que Hacienda o su IdP no
--                                     contestaron por ese documento. Es lo único
--                                     que decide la situación «sin internet» de
--                                     la clave (RN-43); antes contaba cualquier
--                                     reintento, incluido Vault sellado.
--
--  Ninguna fila cambia de significado: todo nace en NULL.
-- ============================================================================
SET NAMES utf8mb4;

ALTER TABLE products
    ADD COLUMN tariff_heading CHAR(12) NULL AFTER unit_of_measure;

ALTER TABLE clients
    ADD COLUMN foreign_address VARCHAR(300) NULL AFTER address;

ALTER TABLE sale_details
    ADD COLUMN tariff_heading CHAR(12) NULL AFTER unit_of_measure;

ALTER TABLE stock_entries
    ADD COLUMN document_type CHAR(2) NULL AFTER payment_terms;

ALTER TABLE fe_documents
    ADD COLUMN unreachable_at DATETIME NULL AFTER last_attempt_at;
