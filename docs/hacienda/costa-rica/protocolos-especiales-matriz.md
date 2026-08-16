# Matriz — Protocolos especiales de grandes compradores (Costa Rica v4.4)

**Fecha:** 2026-07-16 · **País:** Costa Rica (Hacienda v4.4) · **Alcance:** barrido amplio de instituciones públicas, retailers, zona franca y canales transversales.

Qué exige cada gran comprador/institución a los comprobantes de sus proveedores, con qué **estructura del anexo v4.4** se mapea, si **DetCore lo soporta hoy**, y un **escenario de prueba** concreto para el sandbox de Hacienda. Base del ejercicio: la prueba del BCCR (`<OtroContenido codigo="009">`, commit `6266e70`).

> ⚠️ **Los códigos/formatos exactos por empresa suelen ser privados** (portales de onboarding de proveedores). Donde no hay fuente pública se marca `unknown - private`. Los escenarios se anclan en la **estructura** (Otros / Exoneración / references / CodigoComercial / FEE), no en el código propietario de cada quien — que el ERP debe suministrar.

---

## 1. Hallazgos clave

The matrix splits cleanly into three DetCore-support tiers. (1) FULLY SUPPORTED, TESTABLE NOW: the only entity with EXACT public codes is Walmart (Gosocket instructivo) — Otros/OtroTexto codigo=WMNumeroVendedor/WMEnviarGLN/WMNumeroOrden and NC TipoNota/WMNumeroReclamo — making it the single best end-to-end test; DetCore already relays these (commit 6266e70). ICE is the strongest public-institution case: its PO/FI/FT rules map to InformacionReferencia (references[]), NOT the <Otros> commercial node — reference-type 99 with a non-clave Numero (MM-45000xxxxx) is supported because CrValidator only enforces the clave shape for reference codes 1-4/9/11/12/15, not 99. Free-zone Exoneracion TipoDocumentoEX=08 (Intel, DHL Global Forwarding ZF, Boston Scientific CoCode 2380) is fully supported and high-value; note code 08 in the TipoDocumentoEX catalog is unrelated to doc-type 08 ('Depósito de garantía'). UCR is the counterintuitive winner: it is NOT exempt — it takes a reduced 2% RATE via CodigoTarifaIVA=03 (relayed) plus receptor CIIU 8530.1; mapping UCR to <Exoneracion> would be a bug. Both BCCR (641101) and UCR (8530.1) receiver-activity codes are supported via receiver.countrySpecific.economicActivityCode → <CodigoActividadReceptor> (confirmed in CrInvoiceGenerator.cs). (2) MECHANISM SUPPORTED BUT CODE UNKNOWN-PRIVATE: every SICOP public buyer (CCSS, AyA, INS, BNCR, RECOPE, JASEC/ESPH/CNFL) and most private retailers (PriceSmart, Auto Mercado, Unicomer, Monge, Dos Pinos, FIFCO, Purdy) need only a verbatim PO/vendor/GTIN relay — DetCore's otros[] / references[] / commercialCodes[] handle the shape; the specific codigo/format lives behind private onboarding portals and must never be invented. Two disambiguations are load-bearing: BCCR's alleged codigo 009 is UNVERIFIED (do not hardcode), and ICE's 'MM-' prefix is ICE-only (do not reuse for INS/other SICOP buyers). CCSS's tax treatment is NO SUJECIÓN on the line, not an Exoneracion/Exonet node on the sale to it. (3) Nearly every private retailer and the SICOP channel itself impose NO Exoneracion and no FEE — negative controls matter. SICOP needs zero special transformer behavior (server-side clave linkage).

## 2. Soporte de DetCore por estructura del anexo v4.4

| Estructura (nodo v4.4) | Estado | Evidencia (código) |
|---|:---:|---|
| Otros / OtroTexto+OtroContenido (uso comercial no tributario, incl. codigo attr e.g. BCCR 009) | ✅ sí | CanonicalDocument.cs:227 record CanonicalOther(Element, Code, Text) + :51 Otros list; canonical-v1.schema.json $defs.otro (line 375) + top-level 'otros' (line 86); CrInvoiceGenerator.cs:417-449 emits <Otros> with OtroTexto/OtroContenido and the optional codigo attribute; CrInvoiceSchemaProfile.cs OtrosAllowed (true on FE/TE/NC/ND/FEC/FEE, false on REP) |
| Exoneracion (line-level Impuesto/Exoneracion for exempt receivers / exemption authorizations) | ✅ sí | CanonicalDocument.cs:175 record CanonicalExoneration + CanonicalTax.Exoneration (:154); canonical-v1.schema.json tax.exoneration (line 264); CrInvoiceGenerator.cs:904-931 BuildExoneracion; CrValidator.cs:139-147 SupportsExoneracion doc-type guard |
| CodigoComercial (retailer/industry SKU/GTIN product codes on lines) | ✅ sí | CanonicalDocument.cs:278 record CanonicalCommercialCode(Type, Code) + CanonicalLineCountrySpecific.CommercialCodes (:261); canonical-v1.schema.json commercialCodes (line 654, maxItems 5, type enum 01/02/03/04/99); CrInvoiceGenerator.cs:800-805 emits <CodigoComercial> Tipo+Codigo |
| DetalleSurtido (combos/surtidos rendered as one line — manufacturer/importer) | ❌ gap | grep for 'DetalleSurtido'/'Surtido' hits ONLY the .xsd schema files (FacturaElectronica_V4.4.xsd etc.), never CanonicalDocument.cs, canonical-v1.schema.json, CrInvoiceGenerator.cs or CrValidator.cs |
| OtrosCargos (document-level additional charges / third-party levies / timbres) | ✅ sí | CanonicalDocument.cs:203 record CanonicalOtherCharge + :46 OtherCharges list; canonical-v1.schema.json otherCharge (line 323); CrInvoiceGenerator.cs:1224-1251 BuildOtrosCargos + TotalOtrosCargos in ResumenFactura (:1031-1035, :1165); CrValidator.cs:151-158 SupportsOtrosCargos guard |
| DatosImpuestoEspecifico (excise/specific-tax sub-block inside Impuesto) | ❌ gap | grep for 'DatosImpuestoEspecifico'/'CodigoImpuestoOtro' hits ONLY the .xsd files; CrInvoiceGenerator.cs BuildImpuesto (:880-900) emits only Codigo, CodigoTarifaIVA, Tarifa, Monto, Exoneracion — no specific-tax sub-block; CanonicalTax (CanonicalDocument.cs:146) has no fields for it |
| Foreign currency / TipoCambio | ✅ sí | CanonicalDocument.cs:35 ExchangeRate + :36 Currency; canonical-v1.schema.json currency (line 51) + exchangeRate (line 56); CrInvoiceGenerator.cs:235-242 (defaults CRC, requires exchangeRate for non-CRC on Full profile) + :976-978 emits CodigoMoneda+TipoCambio |
| CondicionVenta '99' escape + other '99' free-text escapes | 🟡 parcial | Supported 99 escapes: MedioPagoOtros (CrInvoiceGenerator.cs:1073), CodigoReferenciaOTRO/TipoDocRefOTRO (:1259-1275 + CrValidator.cs:182-196), exoneration TipoDocumentoOTRO/NombreInstitucionOtros (:1428-1441), OtrosCargos TipoDocumentoOTROS (:296), Descuento CodigoDescuentoOTRO (:844-847). GAP: CondicionVenta '99' — grep shows CondicionVentaOtros exists ONLY in the .xsd files; no canonical field (confirmed absent in CanonicalDocument.cs and CrInvoiceGenerator.cs) and it is never emitted |
| FEE (Factura de Exportacion) + PartidaArancelaria + free-zone/export exempt lines | ✅ sí | CrInvoiceSchemaProfile.cs:177-200 FEE profile (LineHasPartidaArancelaria=true, ReceptorAcceptsOtrasSenasExtranjero=true, no BaseImponible/ImpuestoNeto/ImpuestoAsumido); CanonicalLineCountrySpecific.TariffHeading (:248) -> CrInvoiceGenerator.cs:787-790 <PartidaArancelaria>; canonical-v1.schema.json tariffHeading (line 638, 12 chars) + countryProfileReceiverUbicacion excludes FEE (line 696) |

_Notas de soporte relevantes:_
- **Otros / OtroTexto+OtroContenido:** Full round-trip. `element` chooses OtroTexto vs OtroContenido; `code` becomes the codigo attribute (the exact mechanism a BCCR '009' block or a SICOP PO/contract reference would ride on); XSD sequence (all OtroTexto before all OtroContenido) is respected. Legacy top-level `notes` also maps to a codeless OtroTexto. Content is relayed verbatim — DetCore never invents it. **Nested-complement path (Gessa/PriceSmart `retail:Complemento`) — NOT supported, and confirmed NOT supportable via `<OtroContenido>`.** A Forma-C prototype (canonical `otros[].rawContent` → embed the fragment as a child of OtroContenido) was built and **live-tested against Hacienda STAG 2026-07-20 → RECHAZADO with -1 `cvc-complex-type.2.2: Element 'OtroContenido' must have no element [children]`.** Hacienda **does** XSD-validate the incoming comprobante and hard-rejects any child element inside OtroContenido (it is simpleContent). The prototype was **reverted** (canonical, transformer, schema, tests). Corollary: the SWS legacy Word's Gessa(003)/PriceSmart(005/105) embedded-complement approach is not Hacienda-valid — those complements must reach the retailer out-of-band (ekomercio B2B), not embedded in the signed fiscal XML. The 9 SWS example XMLs contain zero nested complements (all Forma A/B), consistent with this. Content is relayed verbatim — DetCore never invents it. NOTE ON SICOP: there is NO SICOP-specific field; SICOP purchase-order/contract data is only supported insofar as the ERP hand-crafts it into an Otros entry (code + text). The exact per-institution codigo/format that a SICOP supplier must use is NOT encoded here and is 'unknown - private' (lives in each institution's supplier-onboarding rules); DetCore is a pure relay for it. REP rejected early (CrInvoiceGenerator.cs:307-313).
- **Exoneracion:** Comprehensive. Full XSD sequence emitted (TipoDocumentoEX1, TipoDocumentoOTRO, NumeroDocumento, Articulo/Inciso, NombreInstitucion, NombreInstitucionOtros, FechaEmisionEX, TarifaExonerada, MontoExoneracion). Enforces Hacienda conditional rules the XSD leaves loose: -478 Articulo mandatory for codes 02/03/06/07/08 (CrInvoiceGenerator.cs:42-43,1421), -479 Inciso required once Articulo present (defaults 0, :919), and TipoDocumento='99'/NombreInstitucion='99' free-text escapes (:1428,:1435). Line drives the exonerado buckets in ResumenFactura (ComputeResumenTotals :1123). ImpuestoNeto = Monto - MontoExoneracion. Doc-type restricted to FE/FEC/TE/NC/ND. This covers the 'exempt entity / authorized-by-law' buyer protocol (TipoDocumento 01..99 incl. 03/04).
- **CodigoComercial:** Up to 5 per line, relayed verbatim in XSD position (after CodigoCABYS, before Cantidad). Type catalog enforced by schema enum (01 seller, 02 buyer, 03 industry SKU/GTIN, 04 internal, 99 other). This is the exact slot big retailers use to require their supplier codes. DetCore does not enforce the conditional 'surtidos need type 03' rule — left to Hacienda (documented as intentional).
- **DetalleSurtido:** No canonical field and no transformer emission for the <DetalleSurtido> sub-element (the manufacturer/importer combo-breakdown carried inside a LineaDetalle). Partial mitigation: CABYS 'surtido' lines can still carry CodigoComercial type 03, but the structured DetalleSurtido decomposition itself is unsupported. Rarely needed (manufacturer/importer only) — flag if a fabricante onboards.
- **OtrosCargos:** Comprehensive. Full XSD sequence (TipoDocumentoOC, TipoDocumentoOTROS, IdentificacionTercero Tipo+Numero, NombreTercero, Detalle, PorcentajeOC, MontoCargo). Caps at 15 (maxOccurs), enforces '99'->chargeTypeOther escape, third-party block emitted only when the full Tipo+Numero pair is present, and TotalOtrosCargos folded into TotalComprobante. Rejected on REP. Relayed as-is; DetCore never invents a charge.
- **DatosImpuestoEspecifico:** Excise / impuesto-específico taxes (e.g. IVA-específico on tobacco/alcohol/cement with the DatosImpuestoEspecifico Cantidad/PorcentajeVolumen/etc. detail) cannot be expressed or emitted. Related limitation: the transformer only emits ONE Impuesto per line and errors on lines with >1 tax (CrInvoiceGenerator.cs:1347-1354 'CostaRica.Transformer.UnsupportedShape'), so multi-tax lines are also unsupported. Only standard IVA (Codigo 01, CodigoTarifaIVA 01-11) is handled.
- **Foreign currency / TipoCambio:** CodigoTipoMoneda/CodigoMoneda/TipoCambio emitted on both Full and RepSlim resumen profiles. Missing exchangeRate on a non-CRC document is rejected pre-transmit ('CostaRica.Transformer.MissingField'). Defaults TipoCambio=1 for CRC. Relayed — DetCore does not fetch/compute the rate.
- **CondicionVenta '99' escape + other '99' free-text escapes:** Nearly all of Hacienda's '99'->free-text companion fields are handled. The one hole is CondicionVenta='99' (Otros): saleCondition is relayed verbatim (CrInvoiceGenerator.cs:200-215) but the XSD-mandated companion <CondicionVentaOtros> (minOccurs=0, required-when-99) has no canonical slot and is never written — so a saleCondition='99' document would emit XML missing CondicionVentaOtros and be rejected by Hacienda. saleCondition is not validated against a catalog either (only against a per-profile allowed set, which is null=any for all types except REP).
- **FEE:** Full FEE path: 12-char PartidaArancelaria slotted only on FEE/NC/ND (LineHasPartidaArancelaria), foreign buyer address via OtrasSenasExtranjero (CrInvoiceGenerator.cs:594-598) instead of Ubicacion, and export-exempt lines forced to CodigoTarifaIVA='10' with FEE rejecting '01' via -101 (handled at :1335-1337 and rateCode relay :1369-1381). FEE-specific slim line shape (jumps Impuesto->MontoTotalLinea) modeled. This covers the free-zone/export protocol.

## 3. Matriz por entidad

### Instituciones públicas / autónomas

| Entidad | Estructura especial | Código / formato | DetCore | Conf. |
|---|---|---|:---:|:---:|
| ICE (Instituto Costarricense de Electricidad) | InformacionReferencia (references[]) — procurement PO | TipoDocIR=99 (Otros)+referenceTypeOther, CodigoReferencia=99+reasonCodeOther, Numero=MM-45000XXXXX; receptor cédula 4000042139 | ✅ sí | high |
| ICE (Instituto Costarricense de Electricidad) | InformacionReferencia — Factura Financiera / Fondos de Trabajo | FI-000000000X (acreedores) or FT-XXXX-<cédula> (fondos de trabajo) in Numero, TipoDocIR/CodigoRef=99 | ✅ sí | high |
| ICE (Instituto Costarricense de Electricidad) | InformacionReferencia — NC anula (correction path) | TipoDocIR=01 (FE), CodigoReferencia=01 (Anula), Numero=50-digit clave of invoice being annulled | ✅ sí | high |
| ICE (Instituto Costarricense de Electricidad) | Exoneracion | n/a — ICE is not IVA-exempt as buyer | ⚪ n/a | high |
| BCCR (Banco Central de Costa Rica) | CodigoActividadReceptor (receiver economic activity, v4.4) | CIIU v4 641101 (from 2025-10-07; v3 651101 legacy) | ✅ sí | high |
| BCCR (Banco Central de Costa Rica) | Otros / OtroContenido (alleged codigo 009) | unknown - private (BCCR_CUENTA_CLIENTE=...;BCCR_ORDEN_PEDIDO=... UNVERIFIED — no public source; do NOT hardcode 009) | ✅ sí | low |
| CCSS (Caja Costarricense de Seguro Social) | Tax treatment: NO SUJECIÓN on the sale to CCSS (line rate/exempt, NOT <Exoneracion>) | ERP-supplied rateCode/exempt on the line; do NOT emit <Exoneracion>/Exonet on the sale TO CCSS (verifier correction: that machinery is for the supplier's OWN input purchases) | ✅ sí | medium |
| CCSS (Caja Costarricense de Seguro Social) | Otros / InformacionReferencia — SICOP/GECO PO | unknown - private (reconciled in SICOP/GECO out-of-band; no fixed codigo published) | ✅ sí | low |
| RECOPE (Refinadora Costarricense de Petróleo) | Otros / OtroContenido — pedido + pedido marco (FO) | unknown - private codigo; goods description + RECOPE pedido number, plus 'pedido marco' FO-prefix for partial deliveries | ✅ sí | medium |
| RECOPE (Refinadora Costarricense de Petróleo) | Exoneracion | n/a — taxable state S.A., IVA charged normally | ⚪ n/a | medium |
| AyA / ICAA (Acueductos y Alcantarillados) | REP (Recibo Electrónico de Pago) on credit sale to a State entity | REP comprobante type (generic v4.4 obligation for credit sales to State, mandatory 2025-09-01; not an AyA-specific code) | ✅ sí | high |
| AyA / ICAA (Acueductos y Alcantarillados) | InformacionReferencia / Otros — SICOP PO | unknown - private (verifier: prefer document-reference path over OtroContenido, per ICE analog) | ✅ sí | low |
| INS (Instituto Nacional de Seguros) | InformacionReferencia / Otros — SICOP orden de pedido | unknown - private (do NOT reuse ICE's MM-45000 prefix; INS field/prefix not published) | ✅ sí | low |
| INS (Instituto Nacional de Seguros) | Exoneracion | n/a — insurance-premium exemption is INS's OUTPUT, not its purchases | ⚪ n/a | high |
| BNCR (Banco Nacional de Costa Rica) | InformacionReferencia / Otros — SICOP PO | unknown - private (do NOT attribute BCCR's codigo 009 to BNCR — distinct entity) | ✅ sí | low |
| BNCR (Banco Nacional de Costa Rica) | Exoneracion | n/a — taxable state commercial bank (IVA perception agent, form D-169) | ⚪ n/a | high |
| Universidad de Costa Rica (UCR) | CodigoTarifaIVA (taxes[].rateCode) = 03 (tarifa reducida 2%) | CodigoTarifaIVA=03 (2%); receptor cédula 4-000-042149 tipo 02 | ✅ sí | high |
| Universidad de Costa Rica (UCR) | CodigoActividadReceptor = 8530.1 (Enseñanza Universitaria) | CIIU 4.4 = 8530.1 (mandatory since 2025-10-06) | ✅ sí | high |
| Universidad de Costa Rica (UCR) | Exoneracion (ANTI-PATTERN — must NOT be used) | N/A — reduced RATE (2%), not an exemption; mapping to <Exoneracion> would be structurally wrong | ⚪ n/a | high |
| JASEC / ESPH / CNFL (distribuidoras eléctricas) | InformacionReferencia / Otros — SICOP OC/HES/acta reference | unknown - private (ESPH strongest: invoice electronically rejected if OC/HES/acta ref omitted; structure/codigo not published) | ✅ sí | low |

### Retailers / grandes privados

| Entidad | Estructura especial | Código / formato | DetCore | Conf. |
|---|---|---|:---:|:---:|
| Walmart de México y Centroamérica (Más x Menos, Palí, Maxi Palí, Walmart CR) | Otros / OtroTexto (Gosocket B2B, codigo attribute) — commercial data | codigo=WMNumeroVendedor (9 digits), WMEnviarGLN (13 digits), WMNumeroOrden (10 digits); PUBLICLY documented | ✅ sí | high |
| Walmart de México y Centroamérica (Más x Menos, Palí, Maxi Palí, Walmart CR) | Otros / OtroTexto — Credit-note typing | codigo=TipoNota (NCCLAIM\|NCProntoPago\|NCOtros\|NCGastos); claim NCs also codigo=WMNumeroReclamo (10 digits) | ✅ sí | high |
| Walmart de México y Centroamérica (Más x Menos, Palí, Maxi Palí, Walmart CR) | CodigoComercial (SKU/GTIN) | unknown - private (no public Walmart CR XML mandate; adversarial grep found zero CodigoComercial/GTIN in the instructivo) | ✅ sí | low |
| PriceSmart CR (Prismar de Costa Rica S.A., 3-101-231707) | Otros / OtroContenido — 'No. de Vendedor' + PriceSmart commercial data | unknown - private (assigned per-supplier 'No. de Vendedor'; exact codigo attribute lives in FinanzaPro template/onboarding) | ✅ sí | medium |
| PriceSmart CR (Prismar de Costa Rica S.A., 3-101-231707) | CodigoComercial (GTIN/UPC per product) | unknown - private (GTIN is the product's own GS1 code; the CodigoComercial Tipo used is not published) | ✅ sí | medium |
| Grupo Auto Mercado (Auto Mercado S.A., 3-101-007186) | CodigoComercial (GTIN/EAN) | unknown - private (product barcode/GTIN listing confirmed at PRODUCT level; XML-mandate NOT documented) | ✅ sí | low |
| Grupo Auto Mercado (Auto Mercado S.A., 3-101-007186) | Exoneracion | n/a — private for-profit retailer, normal IVA | ⚪ n/a | high |
| Unicomer / Gollo (Unión Comercial de Costa Rica S.A.) | CodigoComercial (SKU/GTIN) / Otros (PO) | unknown - private (generic large-retailer inference; no entity-specific public source; servicios.grupogollo.com private) | ✅ sí | low |
| Grupo Monge (GMG Comercial CR S.A., 3-101-590004) | Otros (PO) / CodigoComercial (SKU) — no public protocol | unknown - private (no publicly documented special protocol; do NOT copy BCCR 009) | ✅ sí | low |
| FIFCO (Florida Ice & Farm Co. S.A.) | Otros (PO / licitación) — SAP Ariba comunidadfill | unknown - private (Salesforce portal JS/CSP-gated; PO required in Ariba, XML placement undocumented) | ✅ sí | low |
| FIFCO (Florida Ice & Farm Co. S.A.) | DatosImpuestoEspecifico (FIFCO/Florida Bebidas-as-emisor: alcohol excise) | n/a to buyer role; but a beverage manufacturer emitting via DetCore would need Impuesto Codigo 04 (Bebidas Alcohólicas) specific-tax sub-block | ❌ gap | medium |
| Purdy Motor S.A. (Grupo Purdy) | Otros (PO) / CodigoComercial (part number) — no public protocol | unknown - private (purely speculative; no Purdy proveedores spec exists; Purdy is a SICOP SUPPLIER to the state, not a buyer imposing rules) | ✅ sí | low |

### Zona franca / multinacionales

| Entidad | Estructura especial | Código / formato | DetCore | Conf. |
|---|---|---|:---:|:---:|
| Intel Costa Rica (Componentes Intel de Costa Rica S.A., zona franca) | Exoneracion — TipoDocumentoEX=08 (Exoneración a Zona Franca) | TipoDocumentoEX1=08; NOTE code 08 collides with TipoDocumento(doc-type) 08='Depósito de garantía' — different catalogs; per-transaction authorization Numero is buyer-supplied | ✅ sí | high |
| Intel Costa Rica (Componentes Intel de Costa Rica S.A., zona franca) | Otros / OtroContenido — SAP Ariba PO number | unknown - private (PO required on Ariba invoices; v4.4 has no PO header field; codigo not public) | ✅ sí | medium |
| Boston Scientific de Costa Rica S.R.L. (zona franca) / Establishment Labs | Receptor split + Exoneracion — free-zone entity vs commercial entity | CoCode 2380 = free-zone/EXEMPT (céd 3-102-357469 confirmed via AZOFRAS) → Exoneracion(08); CoCode 2420 = commercial/TAXABLE (céd unverified) → normal IVA | ✅ sí | medium |
| Boston Scientific de Costa Rica S.R.L. (zona franca) / Establishment Labs | Otros — SAP Ariba PO reference | unknown - private (16-char alphanumeric invoice ref in Ariba; PO-in-XML not documented — enforced in Ariba portal, not the comprobante) | ✅ sí | low |
| DHL Global Forwarding Costa Rica Zona Franca S.A. | Exoneracion — TipoDocumentoEX=08 (Zona Franca) | TipoDocumentoEX1=08 (nota técnica 10.1); per-transaction authorization Numero buyer-supplied | ✅ sí | medium |
| DHL Global Forwarding Costa Rica Zona Franca S.A. | Otros / OtroContenido — Tradeshift PO / Cost-Centre (MU) | unknown - private (PO=11-char country-prefixed OR MU=5-digit numeric + PO line number; enforced in Tradeshift, not the XML) | ✅ sí | medium |
| DHL Global Forwarding Costa Rica Zona Franca S.A. | CodigoComercial (SKU/GTIN) | n/a — DHL is a services/logistics buyer, matching is PO/MU-based (verifier refuted a CodigoComercial mandate) | ⚪ n/a | low |

### Transversales

| Entidad | Estructura especial | Código / formato | DetCore | Conf. |
|---|---|---|:---:|:---:|
| SICOP (Sistema Integrado de Compras Públicas) — cross-cutting channel | Base fiscal comprobante only (linkage server-side by clave) | no mandatory XML-embedded code; SICOP reconciles by 50-digit clave + receptor tax id in 'Recepción de Bienes y Servicios' | ⚪ n/a | high |
| SICOP (Sistema Integrado de Compras Públicas) — cross-cutting channel | Per-institution PO/contract reference (Otros vs references[]) | unknown - private per institution; only public exemplar is ICE 'MM-45000xxxxx' (ICE-only, do NOT generalize) | ✅ sí | low |
| Retail EDI / supplier-portal pattern — cross-cutting | CodigoComercial (GTIN/SKU) + Otros (account/PO/cost-centre) | unknown - private per chain (GTIN via GS1; codes live in each portal's onboarding, e.g. Walmart Orbit/Retail Link) | ✅ sí | medium |

### Otros

| Entidad | Estructura especial | Código / formato | DetCore | Conf. |
|---|---|---|:---:|:---:|
| Cooperativa Dos Pinos R.L. | Otros / OtroContenido — PO/requisición (SAP portal) | unknown - private (generic large-buyer inference; UCDP course shows only registration, no invoicing spec) | ✅ sí | low |
| Cooperativa Dos Pinos R.L. | DetalleSurtido (Dos Pinos-as-emisor combos) | n/a to buyer role; but if Dos Pinos (manufacturer) onboards as a DetCore EMISOR of surtido combos, the structure is unsupported | ❌ gap | medium |

## 4. Orden de pruebas recomendado (live sandbox)

De mayor a menor valor (soportado + alta confianza primero; controles negativos al final):

1. Walmart Otros/OtroTexto codigo test — WMNumeroVendedor(9)/WMEnviarGLN(13)/WMNumeroOrden(10) on an FE (only entity with EXACT public codes; supported; high)
2. ICE InformacionReferencia PO — references[] TipoDocIR=99 + Numero='MM-45000123456' on an FE (supported; validates non-clave Numero relays for type 99; high)
3. Intel Exoneracion TipoDocumentoEX=08 (Zona Franca) full sequence on an FE, with Articulo-required (-478) enforcement (supported; high; canonical free-zone case)
4. UCR CodigoTarifaIVA=03 reduced-2% relay on an FE to 4-000-042149 — verify DetCore does NOT infer 13% (supported; high; counterintuitive)
5. BCCR & UCR CodigoActividadReceptor relay — 641101 / 8530.1 into <CodigoActividadReceptor> (supported; high)
6. Walmart NC typing — Otros codigo=TipoNota=NCCLAIM + WMNumeroReclamo(10) on an NC (supported; high)
7. ICE NC anula — references[] TipoDocIR=01/CodigoRef=01/Numero=50-digit clave (supported; high; exercises clave semantic validation)
8. DHL & Boston Scientific free-zone Exoneracion(08) + Boston Scientific receptor split (2380 exempt vs 2420 taxable) — verify per-receptor tax routing (supported; medium-high)
9. AyA credit-sale then REP — saleCondition=02 + PlazoCredito, then a REP; verify RepSlim profile and that Otros is prohibited on REP (supported; high)
10. PriceSmart Otros 'No. de Vendedor' + CodigoComercial GTIN — mechanism relay with private code values (supported; existence high, codes private)
11. RECOPE Otros 'pedido' + 'pedido marco (FO)' free-text relay (supported; medium)
12. CCSS no-sujeción line relay (verify DetCore does NOT synthesize an Exoneracion node on the sale to CCSS) (supported; medium)
13. Negative controls — normal-IVA FE with NO Exoneracion to ICE/RECOPE/INS/BNCR/Auto Mercado (n/a; confirm Aceptado)
14. SICOP baseline — plain valid v4.4 FE to an institutional cédula (n/a; confirms no special transformer behavior needed)

## 5. Gaps estructurales de DetCore surfaced

Four DetCore structural gaps surfaced. (1) DetalleSurtido — no canonical field or transformer emission; a fabricante/importador (e.g. Dos Pinos) billing a mixed-IVA-rate combo as one line cannot decompose it; only partial mitigation via CodigoComercial type 03 on the parent line. (2) DatosImpuestoEspecifico (excise) — the transformer emits only standard IVA (Codigo 01) and errors on any line with >1 Impuesto ('CostaRica.Transformer.UnsupportedShape'); a beverage/alcohol/fuel/tobacco EMISOR (e.g. FIFCO/Florida Bebidas, Impuesto Codigo 04) cannot be processed. Both gaps bite DetCore issuers, not the buyer-side scenarios that are the focus here, but a manufacturer onboarding would hit them. (3) CondicionVenta='99' — saleCondition is relayed but the XSD-mandated companion <CondicionVentaOtros> has no canonical slot and is never emitted, so a 99 sale condition would be rejected by Hacienda; all OTHER '99' free-text escapes (MedioPago, reference TipoDocRefOTRO/CodigoReferenciaOTRO, exoneration TipoDocumentoOTRO/NombreInstitucionOtros, OtrosCargos TipoDocumentoOTROS) ARE handled. (4) Watch-item, not a confirmed gap: references[].ReferenceId carrying a non-clave value for reference-type 99 (ICE's MM-/FI-/FT- numbers) works today because CrValidator scopes the clave check to codes 1-4/9/11/12/15 — this should be explicitly asserted by a live test since DetCore's convention otherwise centers references[].referenceId on the 50-digit clave. Also unverified downstream: SICOP/portal PO placement (references vs Otros) is per-institution and undocumented publicly — do not bake a default codigo into the transformer.

## 6. Escenarios detallados por fila (con fuentes)

Cada fila de la matriz con su escenario de prueba completo y fuentes.

### Instituciones públicas / autónomas

**ICE (Instituto Costarricense de Electricidad) — InformacionReferencia (references[]) — procurement PO** _(✅ sí, conf. high)_
- Código/formato: TipoDocIR=99 (Otros)+referenceTypeOther, CodigoReferencia=99+reasonCodeOther, Numero=MM-45000XXXXX; receptor cédula 4000042139
- Escenario: Emit an FE to receptor 4000042139 with references[]={referenceType:'99', referenceTypeOther:'Otros', reasonCode:'99', reasonCodeOther:'Otros', referenceId:'MM-45000123456'}. Confirm <InformacionReferencia> emits TipoDocIR=99/TipoDocRefOTRO/CodigoReferencia=99/CodigoReferenciaOTRO/Numero verbatim (non-clave Numero must pass CrValidator).
- Fuentes: grupoice.com/documento+facturacion.pdf; CanonicalDocument.cs:307; CrValidator.cs:190

**ICE (Instituto Costarricense de Electricidad) — InformacionReferencia — Factura Financiera / Fondos de Trabajo** _(✅ sí, conf. high)_
- Código/formato: FI-000000000X (acreedores) or FT-XXXX-<cédula> (fondos de trabajo) in Numero, TipoDocIR/CodigoRef=99
- Escenario: Emit an FE with references[].referenceId='FI-0000000001' (or 'FT-1234-0102030405'), referenceType='99', reasonCode='99'. Verify Numero relays verbatim without clave-shape rejection.
- Fuentes: grupoice.com/documento+facturacion.pdf

**ICE (Instituto Costarricense de Electricidad) — InformacionReferencia — NC anula (correction path)** _(✅ sí, conf. high)_
- Código/formato: TipoDocIR=01 (FE), CodigoReferencia=01 (Anula), Numero=50-digit clave of invoice being annulled
- Escenario: Emit an NC to 4000042139 with references[]={referenceType:'01', reasonCode:'01', referenceId:<50-digit clave of the FE>}. This matches DetCore's existing references[].referenceId=clave convention; confirm clave semantic validation passes.
- Fuentes: grupoice.com/documento+facturacion.pdf; reference_hacienda_reference_clave_cascade

**ICE (Instituto Costarricense de Electricidad) — Exoneracion** _(⚪ n/a, conf. high)_
- Código/formato: n/a — ICE is not IVA-exempt as buyer
- Escenario: Negative control: emit a normal-IVA FE to ICE with NO <Exoneracion> node; confirm it validates and is Aceptado (ICE pays IVA).
- Fuentes: grupoice.com/documento+facturacion.pdf

**BCCR (Banco Central de Costa Rica) — CodigoActividadReceptor (receiver economic activity, v4.4)** _(✅ sí, conf. high)_
- Código/formato: CIIU v4 641101 (from 2025-10-07; v3 651101 legacy)
- Escenario: Emit an FE to BCCR with receiver.countrySpecific.economicActivityCode='641101'. Confirm <CodigoActividadReceptor>641101</CodigoActividadReceptor> emits (FE profile = Optional) and passes IsValidCodigoActividad.
- Fuentes: bccr.fi.cr/.../174-Facturacion-Electronica.pdf; CrInvoiceGenerator.cs:129-137

**BCCR (Banco Central de Costa Rica) — Otros / OtroContenido (alleged codigo 009)** _(✅ sí, conf. low)_
- Código/formato: unknown - private (BCCR_CUENTA_CLIENTE=...;BCCR_ORDEN_PEDIDO=... UNVERIFIED — no public source; do NOT hardcode 009)
- Escenario: Mechanism smoke-test only (NOT a confirmed BCCR rule): emit an FE with otros=[{element:'OtroContenido', code:'009', text:'BCCR_CUENTA_CLIENTE=X;BCCR_ORDEN_PEDIDO=Y'}] to prove the codigo attribute round-trips; treat the code value as fictional until BCCR onboarding confirms.
- Fuentes: no public source; CanonicalDocument.cs:227; CrInvoiceGenerator.cs:417-449

**CCSS (Caja Costarricense de Seguro Social) — Tax treatment: NO SUJECIÓN on the sale to CCSS (line rate/exempt, NOT <Exoneracion>)** _(✅ sí, conf. medium)_
- Código/formato: ERP-supplied rateCode/exempt on the line; do NOT emit <Exoneracion>/Exonet on the sale TO CCSS (verifier correction: that machinery is for the supplier's OWN input purchases)
- Escenario: Emit an FE to CCSS relaying the ERP's tax treatment for a non-subject line (e.g. taxes[].rateCode / exempt as supplied). Verify DetCore relays verbatim and does NOT synthesize an Exoneracion node. Never infer exemption.
- Fuentes: siemprealdia.co/.../no-sujecion-al-iva; larepublica.net/.../ordenes-especiales-de-compra; feedback_detcore_no_inferir_calculos

**CCSS (Caja Costarricense de Seguro Social) — Otros / InformacionReferencia — SICOP/GECO PO** _(✅ sí, conf. low)_
- Código/formato: unknown - private (reconciled in SICOP/GECO out-of-band; no fixed codigo published)
- Escenario: If a contract supplies a PO, emit an FE carrying it as an otros free-text entry (or references[]) verbatim; no fixed CCSS codigo to assert.
- Fuentes: racsa.go.cr/.../ccss-implementa-sicop; ccss.sa.cr/proveedores

**RECOPE (Refinadora Costarricense de Petróleo) — Otros / OtroContenido — pedido + pedido marco (FO)** _(✅ sí, conf. medium)_
- Código/formato: unknown - private codigo; goods description + RECOPE pedido number, plus 'pedido marco' FO-prefix for partial deliveries
- Escenario: Emit an FE to RECOPE with otros=[{element:'OtroContenido', text:'Pedido 45000XXXX'}] and, for a partial delivery, a second otros entry 'FO<...>'. Relay verbatim; do NOT invent a codigo (none published). Route PDF/XML to per-order email out-of-band.
- Fuentes: recope.go.cr/.../TERMINOS-DE-REFERENCIA-BIENES-DEM-SICOP.pdf §2.4

**RECOPE (Refinadora Costarricense de Petróleo) — Exoneracion** _(⚪ n/a, conf. medium)_
- Código/formato: n/a — taxable state S.A., IVA charged normally
- Escenario: Negative control: normal-IVA FE, no <Exoneracion>; confirm Aceptado.
- Fuentes: recope TOR §1.2/1.9

**AyA / ICAA (Acueductos y Alcantarillados) — REP (Recibo Electrónico de Pago) on credit sale to a State entity** _(✅ sí, conf. high)_
- Código/formato: REP comprobante type (generic v4.4 obligation for credit sales to State, mandatory 2025-09-01; not an AyA-specific code)
- Escenario: Emit an FE to AyA with saleCondition='02' (crédito) + PlazoCredito; then, on payment, emit a REP referencing it. Verify DetCore's REP profile (RepSlim) emits and that Otros is correctly PROHIBITED on REP.
- Fuentes: siemprealdia.co/.../recibo-electronico-de-pago-rep; CrInvoiceSchemaProfile REP profile; feedback_cr_async_represented_in_poller

**AyA / ICAA (Acueductos y Alcantarillados) — InformacionReferencia / Otros — SICOP PO** _(✅ sí, conf. low)_
- Código/formato: unknown - private (verifier: prefer document-reference path over OtroContenido, per ICE analog)
- Escenario: If AyA supplies a PO, relay it via references[] (preferred) or otros; no AyA-specific codigo to assert.
- Fuentes: aya.go.cr/proveeduria; ICE analog

**INS (Instituto Nacional de Seguros) — InformacionReferencia / Otros — SICOP orden de pedido** _(✅ sí, conf. low)_
- Código/formato: unknown - private (do NOT reuse ICE's MM-45000 prefix; INS field/prefix not published)
- Escenario: Relay a per-contract SICOP order reference via references[] or otros verbatim; assert no fixed INS code.
- Fuentes: grupoins.com/proveeduria-institucional; ins-cr.com SICOP ppt

**INS (Instituto Nacional de Seguros) — Exoneracion** _(⚪ n/a, conf. high)_
- Código/formato: n/a — insurance-premium exemption is INS's OUTPUT, not its purchases
- Escenario: Negative control: normal-IVA FE, no <Exoneracion>.
- Fuentes: grupoins.com proveeduria

**BNCR (Banco Nacional de Costa Rica) — InformacionReferencia / Otros — SICOP PO** _(✅ sí, conf. low)_
- Código/formato: unknown - private (do NOT attribute BCCR's codigo 009 to BNCR — distinct entity)
- Escenario: Relay any supplied SICOP order/contract ref via references[]/otros; no BNCR code to assert.
- Fuentes: sicop.go.cr proveedor payment manual; BNCR SICOP institution page addInst=4000001021

**BNCR (Banco Nacional de Costa Rica) — Exoneracion** _(⚪ n/a, conf. high)_
- Código/formato: n/a — taxable state commercial bank (IVA perception agent, form D-169)
- Escenario: Negative control: normal-IVA FE, no <Exoneracion>.
- Fuentes: elfinancierocr.com/.../banco-nacional-cobrara-13-de-iva

**Universidad de Costa Rica (UCR) — CodigoTarifaIVA (taxes[].rateCode) = 03 (tarifa reducida 2%)** _(✅ sí, conf. high)_
- Código/formato: CodigoTarifaIVA=03 (2%); receptor cédula 4-000-042149 tipo 02
- Escenario: Emit an FE to UCR (4-000-042149) with taxes[].rateCode='03' and the 2% Tarifa/Monto supplied by the ERP. Verify DetCore relays rateCode=03 verbatim into <CodigoTarifaIVA> (does not infer 13%). KEY counterintuitive case.
- Fuentes: vra.ucr.ac.cr/.../Circular-VRA-3-2026.pdf; ANEXOS_Y_ESTRUCTURAS_V4.4 (03=2%); project_cr_canonical_ratecode_codigotarifaiva

**Universidad de Costa Rica (UCR) — CodigoActividadReceptor = 8530.1 (Enseñanza Universitaria)** _(✅ sí, conf. high)_
- Código/formato: CIIU 4.4 = 8530.1 (mandatory since 2025-10-06)
- Escenario: On the same UCR FE, set receiver.countrySpecific.economicActivityCode='8530.1'. Confirm <CodigoActividadReceptor>8530.1</CodigoActividadReceptor> emits and passes IsValidCodigoActividad (6-char with optional decimal).
- Fuentes: vra.ucr.ac.cr/.../Circular-VRA-3-2026.pdf (verifier-added); CrInvoiceGenerator.cs:129-137

**Universidad de Costa Rica (UCR) — Exoneracion (ANTI-PATTERN — must NOT be used)** _(⚪ n/a, conf. high)_
- Código/formato: N/A — reduced RATE (2%), not an exemption; mapping to <Exoneracion> would be structurally wrong
- Escenario: Negative control: confirm the 2% UCR line emits via CodigoTarifaIVA=03 and NO <Exoneracion> node is produced (do not let 'public institution' trigger an exemption path).
- Fuentes: Ley 9635 art.11; VRA-3-2026

**JASEC / ESPH / CNFL (distribuidoras eléctricas) — InformacionReferencia / Otros — SICOP OC/HES/acta reference** _(✅ sí, conf. low)_
- Código/formato: unknown - private (ESPH strongest: invoice electronically rejected if OC/HES/acta ref omitted; structure/codigo not published)
- Escenario: Relay the supplied OC/HES reference via references[] (preferred) or otros verbatim; assert no per-company codigo.
- Fuentes: elfinancierocr.com/.../esph-racsa-factura-electronica; sicop manual F-PS-002

### Retailers / grandes privados

**Walmart de México y Centroamérica (Más x Menos, Palí, Maxi Palí, Walmart CR) — Otros / OtroTexto (Gosocket B2B, codigo attribute) — commercial data** _(✅ sí, conf. high)_
- Código/formato: codigo=WMNumeroVendedor (9 digits), WMEnviarGLN (13 digits), WMNumeroOrden (10 digits); PUBLICLY documented
- Escenario: Emit an FE with otros=[{element:'OtroTexto', code:'WMNumeroVendedor', text:'027313900'}, {element:'OtroTexto', code:'WMEnviarGLN', text:'7407001010862'}, {element:'OtroTexto', code:'WMNumeroOrden', text:'1200666682'}]. Verify all three emit as <OtroTexto codigo='...'> in XSD order (all OtroTexto before any OtroContenido). HIGHEST-VALUE: real public codes.
- Fuentes: gss-latam-sp.custhelp.com/.../Walmart+EBS+LA+CR+GoSocket.pdf; CrInvoiceGenerator.cs:417-449; commit 6266e70

**Walmart de México y Centroamérica (Más x Menos, Palí, Maxi Palí, Walmart CR) — Otros / OtroTexto — Credit-note typing** _(✅ sí, conf. high)_
- Código/formato: codigo=TipoNota (NCCLAIM\|NCProntoPago\|NCOtros\|NCGastos); claim NCs also codigo=WMNumeroReclamo (10 digits)
- Escenario: Emit an NC with otros=[{element:'OtroTexto', code:'TipoNota', text:'NCCLAIM'}, {element:'OtroTexto', code:'WMNumeroReclamo', text:'1234567890'}]. For a Pronto Pago NC, emit only TipoNota=NCProntoPago (no vendor/GLN/PO). Verify emission and OtrosAllowed on NC.
- Fuentes: same Gosocket instructivo PDF

**Walmart de México y Centroamérica (Más x Menos, Palí, Maxi Palí, Walmart CR) — CodigoComercial (SKU/GTIN)** _(✅ sí, conf. low)_
- Código/formato: unknown - private (no public Walmart CR XML mandate; adversarial grep found zero CodigoComercial/GTIN in the instructivo)
- Escenario: Optional: if a supplier is asked for line codes, populate commercialCodes[]={type:'03', code:<GTIN>}; not a documented Walmart XML requirement — do not assume.
- Fuentes: no public source; CrInvoiceGenerator.cs:800-805

**PriceSmart CR (Prismar de Costa Rica S.A., 3-101-231707) — Otros / OtroContenido — 'No. de Vendedor' + PriceSmart commercial data** _(✅ sí, conf. medium)_
- Código/formato: unknown - private (assigned per-supplier 'No. de Vendedor'; exact codigo attribute lives in FinanzaPro template/onboarding)
- Escenario: Emit an FE with otros carrying the assigned vendor number as free-text; requirement EXISTENCE is high but the codigo value is private — relay verbatim, do not invent.
- Fuentes: ayuda.finanzapro.com/.../nodo-otros; edicomgroup.com/.../price-smart

**PriceSmart CR (Prismar de Costa Rica S.A., 3-101-231707) — CodigoComercial (GTIN/UPC per product)** _(✅ sí, conf. medium)_
- Código/formato: unknown - private (GTIN is the product's own GS1 code; the CodigoComercial Tipo used is not published)
- Escenario: Emit an FE line with commercialCodes[]={type:'04' or '03', code:<GTIN/UPC>}. Existence high; specific Tipo private — pick per onboarding, relay verbatim.
- Fuentes: ayuda.finanzapro.com; gs1cr.org

**Grupo Auto Mercado (Auto Mercado S.A., 3-101-007186) — CodigoComercial (GTIN/EAN)** _(✅ sí, conf. low)_
- Código/formato: unknown - private (product barcode/GTIN listing confirmed at PRODUCT level; XML-mandate NOT documented)
- Escenario: Optionally relay commercialCodes[]={type, code:<GTIN>}; treat the fiscal-XML mandate as unconfirmed (Red Auto onboarding).
- Fuentes: exphore.com/.../automercado; redauto.cr (private)

**Grupo Auto Mercado (Auto Mercado S.A., 3-101-007186) — Exoneracion** _(⚪ n/a, conf. high)_
- Código/formato: n/a — private for-profit retailer, normal IVA
- Escenario: Negative control: normal-IVA FE/TE, no <Exoneracion>.
- Fuentes: private retailer nature

**Unicomer / Gollo (Unión Comercial de Costa Rica S.A.) — CodigoComercial (SKU/GTIN) / Otros (PO)** _(✅ sí, conf. low)_
- Código/formato: unknown - private (generic large-retailer inference; no entity-specific public source; servicios.grupogollo.com private)
- Escenario: If confirmed via portal, relay commercialCodes[] and/or an otros PO entry verbatim; no code to assert without onboarding.
- Fuentes: gs1cr.org (generic); servicios.grupogollo.com (private)

**Grupo Monge (GMG Comercial CR S.A., 3-101-590004) — Otros (PO) / CodigoComercial (SKU) — no public protocol** _(✅ sí, conf. low)_
- Código/formato: unknown - private (no publicly documented special protocol; do NOT copy BCCR 009)
- Escenario: No asserted requirement. If portalservicios.grupomonge.com onboarding specifies a PO/SKU, relay via otros/commercialCodes verbatim.
- Fuentes: grupomonge.com; verdugotienda terms (entity confirm)

**FIFCO (Florida Ice & Farm Co. S.A.) — Otros (PO / licitación) — SAP Ariba comunidadfill** _(✅ sí, conf. low)_
- Código/formato: unknown - private (Salesforce portal JS/CSP-gated; PO required in Ariba, XML placement undocumented)
- Escenario: If confirmed, relay the FIFCO PO via otros verbatim; no code to assert (source page returns only a loading shell).
- Fuentes: fifco.my.site.com/comunidadfill (gated); compras@fifco.com

**FIFCO (Florida Ice & Farm Co. S.A.) — DatosImpuestoEspecifico (FIFCO/Florida Bebidas-as-emisor: alcohol excise)** _(❌ gap, conf. medium)_
- Código/formato: n/a to buyer role; but a beverage manufacturer emitting via DetCore would need Impuesto Codigo 04 (Bebidas Alcohólicas) specific-tax sub-block
- Escenario: Flag only: excise sub-block (CantidadUnidadMedida/Porcentaje/Proporcion/ImpuestoUnidad) and multi-tax-per-line are unsupported — a beer/alcohol emisor onboarding hits 'CostaRica.Transformer.UnsupportedShape'.
- Fuentes: grep: DatosImpuestoEspecifico only in .xsd; CrInvoiceGenerator.cs:880-900,1347-1354

**Purdy Motor S.A. (Grupo Purdy) — Otros (PO) / CodigoComercial (part number) — no public protocol** _(✅ sí, conf. low)_
- Código/formato: unknown - private (purely speculative; no Purdy proveedores spec exists; Purdy is a SICOP SUPPLIER to the state, not a buyer imposing rules)
- Escenario: No asserted requirement. If confirmed, relay via otros/commercialCodes verbatim.
- Fuentes: no public source; crhoy.com (Purdy as state supplier)

### Zona franca / multinacionales

**Intel Costa Rica (Componentes Intel de Costa Rica S.A., zona franca) — Exoneracion — TipoDocumentoEX=08 (Exoneración a Zona Franca)** _(✅ sí, conf. high)_
- Código/formato: TipoDocumentoEX1=08; NOTE code 08 collides with TipoDocumento(doc-type) 08='Depósito de garantía' — different catalogs; per-transaction authorization Numero is buyer-supplied
- Escenario: Emit an FE to Intel with a line taxes[].exoneration={documentType:'08', numeroDocumento:<Acuerdo Ejecutivo>, articulo:<n>, inciso:<n>, nombreInstitucion, fechaEmisionEX, tarifaExonerada:13, montoExoneracion}. Verify DetCore emits full <Exoneracion> sequence and enforces -478 Articulo-required for code 08. KEY free-zone case.
- Fuentes: facturele.com/.../exoneraciones-4-4; procomer.com/zona-franca/componentes-intel; CrInvoiceGenerator.cs:904-931

**Intel Costa Rica (Componentes Intel de Costa Rica S.A., zona franca) — Otros / OtroContenido — SAP Ariba PO number** _(✅ sí, conf. medium)_
- Código/formato: unknown - private (PO required on Ariba invoices; v4.4 has no PO header field; codigo not public)
- Escenario: Relay Intel's PO as an otros free-text entry verbatim; do not invent a codigo.
- Fuentes: intel.com invoice-requirements-by-country-region

**Boston Scientific de Costa Rica S.R.L. (zona franca) / Establishment Labs — Receptor split + Exoneracion — free-zone entity vs commercial entity** _(✅ sí, conf. medium)_
- Código/formato: CoCode 2380 = free-zone/EXEMPT (céd 3-102-357469 confirmed via AZOFRAS) → Exoneracion(08); CoCode 2420 = commercial/TAXABLE (céd unverified) → normal IVA
- Escenario: Two documents: (1) FE to 3-102-357469 with taxes[].exoneration.documentType='08' (zona franca); (2) FE to the 2420 taxable entity with normal 13% IVA and NO exoneration. Verify DetCore routes the correct tax treatment per receptor. Establishment Labs = unknown-private (do not assume it mirrors BSCI).
- Fuentes: bostonscientific.com Ariba CR PDF (CoCode split); azofras.com (3-102-357469); facturele.com code 08

**Boston Scientific de Costa Rica S.R.L. (zona franca) / Establishment Labs — Otros — SAP Ariba PO reference** _(✅ sí, conf. low)_
- Código/formato: unknown - private (16-char alphanumeric invoice ref in Ariba; PO-in-XML not documented — enforced in Ariba portal, not the comprobante)
- Escenario: Optionally relay the Ariba PO via otros verbatim; placement in the Hacienda XML is inferred, not required.
- Fuentes: bostonscientific.com Ariba CR PDF

**DHL Global Forwarding Costa Rica Zona Franca S.A. — Exoneracion — TipoDocumentoEX=08 (Zona Franca)** _(✅ sí, conf. medium)_
- Código/formato: TipoDocumentoEX1=08 (nota técnica 10.1); per-transaction authorization Numero buyer-supplied
- Escenario: Emit an FE to the DHL free-zone entity with taxes[].exoneration.documentType='08' + full sequence; verify emission + Articulo-required enforcement.
- Fuentes: procomer.com/zona-franca/dhl-global-forwarding; facturele.com code 08

**DHL Global Forwarding Costa Rica Zona Franca S.A. — Otros / OtroContenido — Tradeshift PO / Cost-Centre (MU)** _(✅ sí, conf. medium)_
- Código/formato: unknown - private (PO=11-char country-prefixed OR MU=5-digit numeric + PO line number; enforced in Tradeshift, not the XML)
- Escenario: Relay DHL PO or 5-digit MU via otros verbatim; XML placement is inferred, codigo private.
- Fuentes: dhl.support.tradeshift.com/.../360017251599

**DHL Global Forwarding Costa Rica Zona Franca S.A. — CodigoComercial (SKU/GTIN)** _(⚪ n/a, conf. low)_
- Código/formato: n/a — DHL is a services/logistics buyer, matching is PO/MU-based (verifier refuted a CodigoComercial mandate)
- Escenario: No line-code test warranted.
- Fuentes: verifier: no public source, refuted

### Transversales

**SICOP (Sistema Integrado de Compras Públicas) — cross-cutting channel — Base fiscal comprobante only (linkage server-side by clave)** _(⚪ n/a, conf. high)_
- Código/formato: no mandatory XML-embedded code; SICOP reconciles by 50-digit clave + receptor tax id in 'Recepción de Bienes y Servicios'
- Escenario: Emit a plain valid v4.4 FE to any institutional receptor's cédula; confirm no SICOP-specific node is needed (SICOP needs no special transformer behavior).
- Fuentes: sicop.go.cr proveedor manuals; tutorial.avatarsys.app

**SICOP (Sistema Integrado de Compras Públicas) — cross-cutting channel — Per-institution PO/contract reference (Otros vs references[])** _(✅ sí, conf. low)_
- Código/formato: unknown - private per institution; only public exemplar is ICE 'MM-45000xxxxx' (ICE-only, do NOT generalize)
- Escenario: Per-issuer/per-receptor config: relay the institution's PO via references[] (preferred) or otros verbatim; assert no SICOP-transversal codigo.
- Fuentes: grupoice.com facturacion PDF (ICE-only)

**Retail EDI / supplier-portal pattern — cross-cutting — CodigoComercial (GTIN/SKU) + Otros (account/PO/cost-centre)** _(✅ sí, conf. medium)_
- Código/formato: unknown - private per chain (GTIN via GS1; codes live in each portal's onboarding, e.g. Walmart Orbit/Retail Link)
- Escenario: Generalized relay test: commercialCodes[] for GTIN and otros[] for account/PO — both round-trip verbatim (already proven concretely by the Walmart rows). GTIN→CodigoComercial is an inference, not a documented mandate; only Walmart's Otros codes are publicly fixed.
- Fuentes: gs1cr.org/sistema-gs1/comercio-electronico; walmartcentroamerica.com/proveedores

### Otros

**Cooperativa Dos Pinos R.L. — Otros / OtroContenido — PO/requisición (SAP portal)** _(✅ sí, conf. low)_
- Código/formato: unknown - private (generic large-buyer inference; UCDP course shows only registration, no invoicing spec)
- Escenario: If Dos Pinos supplies a PO, relay via otros verbatim; no code to assert.
- Fuentes: universidad.dospinos.com course id=221 (registration-only)

**Cooperativa Dos Pinos R.L. — DetalleSurtido (Dos Pinos-as-emisor combos)** _(❌ gap, conf. medium)_
- Código/formato: n/a to buyer role; but if Dos Pinos (manufacturer) onboards as a DetCore EMISOR of surtido combos, the structure is unsupported
- Escenario: Flag only: a fabricante like Dos Pinos billing a mixed-IVA-rate combo as one line cannot express <DetalleSurtido> in DetCore (canonical + transformer both lack it). Mitigation: CodigoComercial type 03 on the parent line only.
- Fuentes: grep: DetalleSurtido only in .xsd; not in CanonicalDocument/CrInvoiceGenerator

## 7. Apéndice — resumen por entidad (canal de compra, exención, confianza)

| Entidad | ¿Exenta? | Canal de compra | Conf. | Corrección clave del verificador |
|---|:---:|---|:---:|---|
| ICE (Instituto Costarricense de Electricidad) | no | SICOP / ARIBA / Proveeduría en Línea (PEL); invoices are received and screened by ICE's own "FISCO" (Factura Integrador de Servicios Comerciales y Operativos) validation system, and the supplier must ALSO email the XML+P | high |  |
| BCCR (Banco Central de Costa Rica) | no | SICOP (public procurement / expediente electrónico); electronic-invoice RECEPTION via the EVEX platform (supplier registers in EVEX using BCCR's "guía de comprobantes electrónicos") | high | The finding is accurate and appropriately calibrated. Adversarial checks upheld it: (1) The only high-confidence special requirement — BCCR's receptor CIIU code (v4 641101 from 202 |
| CCSS (Caja Costarricense de Seguro Social) | yes | SICOP (100% of purchases since 2021, all 160 unidades de compra) + internal GECO (Sistema de Gestión de Compras) for purchase orders + its own e-invoice validation module (aissfa.ccss.sa.cr/factura) | medium | The finding's biggest error is a conflation of two distinct IVA mechanisms in the "Exoneracion" requirement. (1) A DIRECT sale from a supplier to CCSS is treated as NO SUJECIÓN (ou |
| RECOPE (Refinadora Costarricense de Petroleo S.A.) | no | SICOP for tendering/ordering, but invoices delivered by EMAIL (RECOPE explicitly does NOT use the SICOP payment module) | medium | The finding survives adversarial verification well; it is honest and its confidence levels are appropriately calibrated. Two refinements: (1) The cited TOR PDF (and its own tramite |
| Instituto Costarricense de Acueductos y Alcantarillados (AyA / ICAA) | no | SICOP | medium | Two adjustments. (1) The REP obligation is accurate and well-sourced but is a GENERIC fiscal rule for any credit sale to a State entity, not a special requirement AyA imposes -- it |
| INS (Instituto Nacional de Seguros) | no | SICOP | medium | The finding is accurate and honest overall. One calibration note: the load-bearing SICOP order-reference-in-comprobante requirement is downgraded from a firm claim to 'plausible/in |
| Banco Nacional de Costa Rica (BNCR) | no | SICOP | medium | The finding is honest, well-calibrated, and its core reasoning survives adversarial checking. Two adjustments: (1) The <Otros> SICOP-reference requirement is rated "medium" but sho |
| Universidad de Costa Rica (UCR) — cédula jurídica 4-000-042149 | no | SICOP (registro obligatorio, Ley 9986) + portal interno propio GECO (geco.ucr.ac.cr); recepción de comprobantes por correo electrónico | high | The core, counterintuitive claim (2% reduced IVA via rateCode 03, NOT exemption) is solid and survives adversarial verification against UCR's own circular and the official Hacienda |
| JASEC / ESPH / CNFL (distribuidoras eléctricas de Costa Rica) | unknown | SICOP | medium | Two corrections/caveats. (1) Structure attribution: the finding routes the SICOP PO/contract reference to <Otros>/<OtroContenido> as a 'convention', but no source ties these entiti |
| Walmart de Mexico y Centroamerica (CR: Mas x Menos, Pali, Maxi Pali, Walmart) | no | Own supplier portal / B2B platform (Gosocket). Suppliers must send facturas/notas de credito to Walmart through Gosocket, which runs a commercial validation ("semaforo" accept/reject) on top of the Hacienda-approved XML. | high | The finding survives adversarial verification almost entirely intact. The core claim is unusually well-sourced: I fetched the cited custhelp.com PDF, extracted its text (25-page 'W |
| PriceSmart Costa Rica (Prismar de Costa Rica, S.A., cédula jurídica 3-101-231707) | no | own supplier web service (proprietary) + optional X12 EDI (EDICOM); NOT SICOP | high | Two accuracy notes, not refutations. (1) Source authority: every citation traces back to FinanzaPro, a third-party billing SaaS provider's help center — NOT to PriceSmart's own sup |
| Grupo Auto Mercado (Auto Mercado S.A., céd. jurídica 3-101-007186) | no | own supplier portal (Red Auto / redauto.cr, SRM); not SICOP | medium | The finding is honest and correctly calibrated overall; no invented codes, and speculative items are properly flagged as 'unknown - private'. Two refinements: (1) The CodigoComerci |
| Unicomer / Gollo (Unión Comercial de Costa Rica, S.A.) | no | own supplier portal (private) — unknown; likely EDI/GS1 for catalog/orders | low | No factual correction needed — the finding is accurate and honestly self-labeled. Refinement: the two 'specialRequirements' are generic large-retailer inferences with zero entity-s |
| Grupo Monge (GMG Comercial Costa Rica S.A., cédula jurídica 3-101-590004; nombres comerciales GMG / Tiendas Monge, El Verdugo, etc.) | no | own supplier portal (unconfirmed) — a host "portalservicios.grupomonge.com" appears in search results but is login-gated / not publicly resolvable; NOT SICOP (SICOP is for public institutions only, and Grupo Monge is a p | high | No correction needed — the finding survives adversarial review. Minor refinements: (1) The cédula jurídica 3-101-590004 and entity identity (GMG Comercial Costa Rica S.A. = Tiendas |
| Cooperativa de Productores de Leche Dos Pinos R.L. ("Dos Pinos") | no | own supplier portal (SAP-based). Dos Pinos runs a private supplier portal with new-supplier registration, qualification, requisitions/POs and an access manual (evidenced by its "Universidad Cooperativa Dos Pinos" course  | high | The finding is honest and well-caveated; no invented codes. Two adjustments: (1) The single 'specialRequirement' (PO reference in <Otros>/<OtroContenido>) should be treated as UNKN |
| FIFCO (Florida Ice & Farm Co., S.A.) | no | own supplier portal (Salesforce community "comunidadfill" at fifco.my.site.com) + compras@fifco.com for onboarding/quotation; NOT SICOP (private for-profit company) | low | The finding is honest and well-calibrated: no invented codes, both special requirements explicitly downgraded to low/'unknown - private', and the private-portal (comunidadfill Sale |
| Purdy Motor S.A. (Grupo Purdy) — automotriz, Costa Rica | no | own supplier portal / unknown - private (no publicly documented SICOP/EDI buyer channel) | high | The finding's substantive conclusion is sound and honestly hedged — no correction to its bottom line. One calibration downgrade: the two 'special requirements' (Otros PO/reference  |
| Intel Costa Rica (zona franca) — operates locally as "Componentes Intel de Costa Rica" / "Intel Free Trade Zone Park, S.A." under the CR Régimen de Zona Franca | yes | own supplier portal / EDI — SAP Business Network (formerly Ariba); NOT SICOP (SICOP is for public institutions only, Intel is private). Local CR suppliers still issue the Hacienda-authorized comprobante electrónico and,  | medium | Two corrections. (1) Entity name: PROCOMER's official zona-franca directory lists the beneficiary as "COMPONENTES INTEL DE COSTA RICA, S.A." (the LEI registry records it as S.R.L.) |
| Boston Scientific / Establishment Labs (dispositivos médicos, zona franca) — Costa Rica | yes | SAP Ariba Network / SAP Business Network (Boston Scientific — confirmed, supplier.ariba.com). NOT SICOP (private multinationals, not public institutions). Establishment Labs channel = unknown (no public source; likely SA | medium | The finding is honest and directionally correct, but over-attributes specific identifiers to the Boston Scientific PDF. I extracted the full text of the cited PDF (https://www.bost |
| DHL (Costa Rica) — logistics & services, including DHL Global Forwarding Zona Franca (Costa Rica) S.A. | yes | Own supplier portal / EDI (DHL Supply Chain invoices via Tradeshift; DHL Global Forwarding via MyDHLi / PO Management). NOT SICOP — DHL is a private multinational, not a public institution, so it does not procure through | medium | Two upgrades and one caveat. (1) The finding's own hedge on the exemption code can be resolved: TipoDocumentoEX code 08 = "Exoneración a Zona Franca" is confirmed as a real v4.4 co |
| SICOP (Sistema Integrado de Compras Públicas) — protocolo transversal | unknown | SICOP (national public e-procurement platform, sicop.go.cr). SICOP is the CHANNEL itself, not a buyer entity. Suppliers must be enrolled in the SICOP Registro de Proveedores (requires a BCCR/authorized digital signature) | high | Minor refinement, not a refutation. The ICE "MM-45000xxxxx" purchase-order reference is not merely free "reference text": ICE's supplier documentation specifies it is carried in th |
| Prácticas de EDI / portales de proveedores en retail CR (transversal) — patrón de convenciones que grandes compradores imponen a los comprobantes de sus proveedores | unknown | Mixto según tipo de comprador. Cadenas de retail privadas: portal de proveedores propio + EDI (ej. Walmart Centroamérica — Orbit para órdenes de compra, Retail Link/APIS para pagos; GS1 EDI con GTIN/GLN). Instituciones p | medium | El finding es honesto y está bien hedgeado; los códigos concretos por comprador están correctamente marcados unknown-private (no inventados). Dos correcciones/matices tras verifica |

---

## Nota metodológica

Generado por un workflow de 22 entidades (47 agentes: fundamentos del anexo v4.4 + auditoría de soporte en DetCore, investigación web por entidad, verificación adversarial de cada hallazgo, y síntesis). Los hallazgos de código citan archivo:línea de DetCore; los de empresa citan fuentes públicas y marcan `unknown - private` cuando no hay documentación abierta. Ninguna prueba live se ejecutó todavía — esta matriz es el insumo para la Fase 2 (emisión contra el sandbox de Hacienda).
