"""Los «no» del servidor, en código y datos (RN-30).

El backend no escribe texto para una persona. Devuelve un código y los datos con
los que se arma la frase, y la frase la arma el POS —que es el único que sabe en
qué idioma está mirando quien la va a leer—:

    {"detail": {"code": "insufficient_stock",
                "product": "Arroz", "available": 2, "requested": 5}}

Antes cada `raise` traía su oración en español. Un cajero brasileño veía media
aplicación en portugués y los errores en español, justo cuando más necesita
entender qué pasó.

**Todo `HTTPException` del backend se construye acá.** No es una preferencia de
estilo: `tests/test_error_codes.py` lee el árbol de sintaxis de `app/` y tumba
`pytest` si aparece un `HTTPException(...)` en cualquier otro lado. Sin ese
guardián la regla dura hasta el primer apuro.

Los códigos son los de esta lista y nada más —el mismo guardián lo comprueba—.
Están en inglés como todo el código; el español vive en los catálogos del POS
(`frontend/messages/{locale}/errors.json`), y ahí tiene que haber una entrada
por cada código de acá.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

#: Los datos que acompañan al código son los que el POS necesita para armar la
#: frase. Van en inglés y con el nombre que ya tienen en el API (`product_id`,
#: `barcode`, `sale_number`), no con el que tendría la oración.
CODES: frozenset[str] = frozenset(
    {
        # --------------------------------------------------------- sesión
        # Un solo código para «no hay token», «está mal firmado» y «venció»:
        # distinguirlos por fuera no le sirve a nadie más que a quien ataca.
        "unauthorized",
        "no_company_in_token",
        "membership_inactive",
        "admin_only",
        "invalid_credentials",
        # `state` es el estado de la suscripción tal como está en la base
        # ('suspendida', 'vencida', 'cancelada'). Es un valor, no un código:
        # viaja como dato y el POS lo traduce.
        "company_blocked",
        "membership_not_found",
        "invalid_invitation_action",
        "invitation_already_accepted",
        # ------------------------------------------------- soporte (F3, RN-4)
        # El token no es de soporte, o dejó de serlo mientras estaba adentro.
        "support_only",
        # La suscripción venció y se le pasó la gracia: se consulta y se cierra
        # la caja, no se vende. `state` es el estado efectivo.
        "subscription_read_only",
        # Soporte mirando de prestado: entrar como es para diagnosticar.
        "impersonation_read_only",
        # `resource` es 'branches', 'terminals' o 'users'; `current` y `max`, la
        # cuenta. El POS arma «Ya tiene 3 cajas y el plan permite 3».
        "plan_limit_reached",
        "company_not_found",
        "plan_not_found",
        # `afiliado` y `compania`: el par que ya está tomado.
        "company_already_exists",
        "invalid_company_state",
        "support_cannot_be_member",
        # ------------------------------------------ módulos por plan (F10, RN-49)
        # `module` es 'purchases', 'accounting' o 'payroll'. El POS arma «Su plan
        # no incluye Contabilidad». Solo lo levantan las escrituras: un módulo
        # apagado deja lo que ya existe en solo lectura (RN-50).
        "module_not_in_plan",
        # ----------------------------------------------------------- caja
        # Cuatro códigos para la misma regla —la caja es de quien la abrió—
        # porque son cuatro frases distintas: consultar, abrir, mover, cerrar.
        "cash_read_not_yours",
        "cash_open_not_yours",
        "cash_movement_not_yours",
        "cash_close_not_yours",
        "cash_session_not_found",
        "cash_session_not_yours",
        "cash_already_open",
        "cash_opening_negative",
        # Uno solo, contra los dos mensajes distintos que había para la misma
        # situación (mover efectivo y cerrar sin caja abierta).
        "cash_no_open_session",
        "cash_insufficient",
        "cash_invalid_movement_type",
        "cash_amount_not_positive",
        "cash_missing_reason",
        "cash_counted_negative",
        # --------------------------------------------------------- ventas
        "duplicate_sale_number",
        "empty_sale",
        "invalid_sale_line",
        # `method` es el valor que llegó. Desde T-1104 el método de pago de una
        # venta es un conjunto cerrado: con texto libre, un «Efectvo» con dedo de
        # más entraba sin avisar, no sumaba al efectivo esperado del arqueo y
        # aparecía como una fila propia en el reporte de métodos de pago.
        "invalid_sale_payment_method",
        # `document_type` es el valor que llegó. Del mostrador salen dos: '01'
        # factura y '04' tiquete (RN-85). Lo demás es un cliente roto.
        "invalid_sale_document_type",
        # Factura sin cliente. La factura electrónica exige un receptor
        # identificado; sin él, lo que se emite es un tiquete (RN-85).
        "invoice_needs_receiver",
        # `document_type`: la compañía no emite ese comprobante (RN-88). La
        # pantalla no lo ofrece; llegar acá es una pantalla vieja o el API.
        "document_type_not_enabled",
        # Factura a un cliente del extranjero (RN-87, T-727): lo suyo es la
        # factura de exportación, o un tiquete.
        "invoice_needs_resident",
        # Exportación sin cliente, o a uno del país.
        "export_needs_receiver",
        "export_needs_foreign_receiver",
        # `client_id`: el cliente del extranjero no tiene dirección (RF-78).
        "export_needs_foreign_address",
        # `product_id`, `name`: una mercancía de la venta sin partida
        # arancelaria (RF-78). Se arregla en la ficha del producto.
        "export_line_needs_tariff_heading",
        # `product_id`, `name`, `tax_code`: la exportación no admite la tarifa
        # 01 ni la 11 (T-720).
        "export_tariff_not_allowed",
        # `tariff_heading`: una partida que no son doce dígitos.
        "invalid_tariff_heading",
        # `max_length`: una dirección extranjera más larga que lo que admite
        # el XML.
        "invalid_foreign_address",
        "product_not_found",
        "product_without_price",
        "insufficient_stock",
        # `field` es 'subtotal', 'tax' o 'total': el nombre del campo en el API,
        # no la palabra de la oración.
        "totals_mismatch",
        "insufficient_payment",
        "sale_not_found",
        "sale_failed",
        # --------------------------------------------------- devoluciones
        "empty_return",
        "missing_return_reason",
        "not_sold_in_this_sale",
        "invalid_return_quantity",
        "excessive_return",
        "return_not_found",
        "return_failed",
        # `sale_id`: anular es el comprobante entero (RN-89). Una venta con
        # devoluciones ya no se anula —lo que queda se devuelve—, y anular sin
        # devolver todo no es anular.
        "annul_after_return",
        "annul_must_be_full",
        # `product_id`: la línea ya tiene una NC por monto (T-726). Devolverla
        # reembolsaría dos veces la misma plata; lo que falte va en otra nota.
        "return_after_credit_note",
        # `sale_id`: una venta con notas por monto ya no se anula (T-726).
        "annul_after_note",
        # ---------------------------------------- notas por monto (T-726)
        "note_not_found",
        "note_failed",
        # `sale_id`: la venta no fue comprobante; no hay qué referenciar.
        "note_needs_document",
        # `document_type`: no es ND ni NC.
        "invalid_note_type",
        # `document_type` y `reference_code`: un motivo que esa nota no admite
        # en un mostrador de contado —hoy solo el '02'—.
        "invalid_note_reason",
        "note_reason_required",
        "empty_note",
        # `product_id`: la venta no llevaba ese producto.
        "note_line_not_in_sale",
        # `product_id`: el monto de la línea en cero o negativo.
        "invalid_note_amount",
        # `product_id`, `available` y `requested`: una NC por más de lo que
        # queda de la línea. Pasarse sería reembolsar lo que nunca se pagó.
        "credit_exceeds_line",
        # ------------------------------------------------------- entradas
        "empty_entry",
        "invalid_entry_source",
        "duplicate_document",
        "invalid_entry_line",
        "entry_product_not_found",
        "entry_missing_barcode",
        "barcode_taken",
        "entry_line_without_product",
        "entry_not_found",
        "entry_already_cancelled",
        "entry_cannot_cancel",
        "entry_failed",
        "entry_cancel_failed",
        # ------------------------------------------------------- catálogo
        "product_has_sales",
        # F15 (RN-98): la existencia ya no se edita desde la ficha —se mueve
        # con una entrada, una salida o una toma— y un producto con kárdex no
        # se borra, se desactiva. `movements` dice cuántas filas lo sostienen.
        "stock_not_editable",
        "product_has_movements",
        # RN-101: el mínimo propio es un entero de cero para arriba o nulo.
        "min_stock_negative",
        # El kárdex se lee por producto o por documento; sin ninguno de los dos
        # no hay qué listar, y una lista vacía diría «nunca se movió».
        "kardex_filter_required",
        # Las salidas con motivo (RN-99) y su catálogo. `reason_code` y no
        # `code`, que es el parámetro de `api_error` y ya hizo tropezar dos
        # veces. `reason_is_system` sirve para las dos cosas que no se le hacen
        # al motivo de la toma: elegirlo en una salida y desactivarlo.
        "reason_not_found",
        "reason_inactive",
        "reason_is_system",
        "reason_code_taken",
        "exit_not_found",
        "exit_cancelled",
        "empty_exit",
        "invalid_exit_line",
        # La toma física (RN-100). `count_already_open` trae la sucursal y la
        # categoría de la que ya está abierta; `count_outside_scope`, el
        # producto y su categoría.
        "count_not_found",
        "count_not_open",
        "count_already_open",
        "count_outside_scope",
        "count_has_no_lines",
        "category_name_taken",
        # `tax_code` es el código que llegó. Los válidos son los once de la nota
        # 8.1 del anexo de Hacienda, y no se corrigen solos: un `"8"` puede ser
        # el `08` general o un dedazo (RN-76).
        "invalid_tax_code",
        # ------------------------------------------- categorías de dos niveles
        "category_not_found",
        # `category_id` es la madre que ya es hija: colgar de ella haría un
        # tercer nivel (RN-5).
        "category_too_deep",
        # La otra mitad de RN-5: la que se quiere volver hija tiene hijas.
        # `children` es cuántas, porque la frase las cuenta.
        "category_has_children",
        "category_self_parent",
        # RN-7: con productos o con hijas no se borra, se desactiva. Van las dos
        # cuentas —`products` y `children`— porque quien lo lee necesita saber
        # qué mover primero.
        "category_in_use",
        # RN-6: el producto va en la hoja. `name` y `children` para poder decir
        # «Bebidas tiene 3 subcategorías: elija una».
        "category_needs_subcategory",
        "category_inactive",
        # `expected` y `received`: reordenar exige la lista completa de
        # hermanas, y con una parcial el orden queda sin definir.
        "category_reorder_incomplete",
        # ------------------------------------------------------------- CABYS
        # `value` y `reason` ('empty' | 'not_digits' | 'bad_length'): el código
        # del catálogo son trece dígitos, y eso se comprueba antes de salir a la
        # red porque es una regla del catálogo, no algo que haya que preguntar.
        "cabys_invalid_code",
        # `code`: Hacienda contestó y dijo que ese código no existe. Es distinto
        # de no haber podido preguntar, que no es un error sino una degradación
        # con aviso (RNF-4) y viaja en el cuerpo de una respuesta que sí llega.
        "cabys_not_found",
        # ------------------------------------------------------- personas
        "person_identification_taken",
        "email_taken",
        "person_not_found",
        "person_not_yours",
        "client_identification_taken",
        "client_not_found",
        "client_update_failed",
        # `reason` dice qué le falta a la exoneración, con el código del dominio
        # (`missing_article`, `points_out_of_range`, …). Es un solo código y no
        # ocho porque los ocho motivos se arreglan en el mismo formulario y con
        # el mismo gesto: completar el campo que falta (RN-78).
        "invalid_exemption",
        "invalid_role",
        "user_not_found",
        "user_not_yours",
        "last_admin",
        # ------------------------------------------------ compras (F10)
        "supplier_not_found",
        # `name`: comprarle a un proveedor desactivado. No se reactiva solo;
        # suele ser un proveedor mal elegido en la lista.
        "supplier_inactive",
        # `identification` y `name`: la cédula repetida y de quién ya es. La
        # misma identificación es el mismo proveedor, y dos fichas del mismo
        # mayorista se reparten sus compras sin que ninguno de los dos saldos
        # sea el que se le debe.
        "supplier_identification_taken",
        # Los dos de la identificación de Hacienda. Van sin prefijo de proveedor
        # a propósito: `companies` (T-621) y `clients` (T-617) tienen el mismo
        # par de columnas y les sirve el mismo «no».
        "invalid_identification_type",
        "identification_required",
        # Un cliente sin tipo y con una cédula que no lo deja deducir (T-617): el
        # tipo va en el receptor del comprobante, y adivinarlo es un rechazo.
        "identification_type_required",
        # La compañía emite y no tiene cédula de emisor, o no cabe en la clave
        # (`reason`: `missing` o `invalid`). La corrige soporte (RN-45, T-705).
        "issuer_identification_required",
        # ------------------------------------------ abonos a proveedor (T-1010)
        # `balance` y `requested`: se quiso abonar más de lo que se debe de esa
        # compra. No se ajusta al saldo en silencio, porque o es un dedo de más
        # o el abono va a otra factura, y las dos las arregla una persona.
        "payment_exceeds_balance",
        "payment_not_positive",
        # `method`: solo 'cash', 'transfer' y 'other'. Uno mal escrito se
        # escaparía del `if` del efectivo y el turno cerraría con un sobrante
        # igual a lo que se pagó (RN-56).
        "invalid_payment_method",
        # Abonar a una compra ya anulada. Pasa de verdad cuando alguien la anula
        # mientras otro tiene abierta la pantalla de saldos, así que no alcanza
        # con esconder el botón.
        "purchase_cancelled",
        "payment_failed",
        # `entry_id` y `payments`: anular una compra con abonos los dejaría
        # colgando de un documento que no existe, y con ellos la plata que sí
        # salió. La cuenta va porque la frase la dice: deshacer uno o siete
        # abonos no es la misma tarea (RN-57).
        "purchase_has_payments",
        # Anular una compra sin decir por qué. En una entrada no hace falta; en
        # una compra el motivo es parte del requisito (RF-46), porque es lo que
        # le queda al proveedor cuando reclame la factura.
        "void_reason_required",
        # ---------------------------------------------- contabilidad (F11)
        # Activar dos veces. No es prolijidad: la segunda vez volvería a sembrar
        # sobre un libro con movimiento y podría cambiar el mapeo bajo los
        # asientos que ya existen, que es lo que RN-62 prohíbe.
        "accounting_already_active",
        # `debits` y `credits`: los saldos iniciales que dictó el contador no
        # cuadran. Van las dos sumas porque quien lo escribió necesita ver por
        # cuánto, y con eso sabe qué línea le falta.
        "invalid_opening_balance",
        # El 500 de este módulo, como `sale_failed` y `payment_failed`: algo se
        # rompió y la unidad de trabajo ya revirtió. `cause` va para el registro,
        # no para mostrar.
        "accounting_failed",
        # Estaba dos veces —acá y arriba, entre los de usuarios— porque lo
        # levantan dos sitios que hablan de cosas distintas: seis de
        # `crud_accounting`, con `account_id`, sobre una cuenta del catálogo, y
        # uno de `/users/membership`, sin datos, cuando no hay cuenta con ese
        # correo. Como conjunto daba igual y la segunda entrada no hacía nada.
        # Queda una sola; que un código sirva para dos cosas es otro asunto y
        # está anotado en T-925.
        "account_not_found",
        # `account_code`: dos cuentas con el mismo código harían ambiguo todo
        # asiento que las nombre, y el código es justo lo que el contador lee.
        #
        # El dato se llama `account_code` y no `code` en los tres porque `code` es
        # el nombre del parámetro de `api_error`: pasarlo como dato choca con él.
        "account_code_taken",
        # `account_code`: es de sistema y la necesita el mapeo (RN-64). Sin ella,
        # el papel que la usaba se queda sin dónde caer. Renombrarla sí se puede:
        # el mapeo apunta al id.
        "account_is_system",
        # `account_code` y `lines`: tiene historia. Borrarla dejaría a los
        # asientos que la nombran sin poder decir contra qué se hicieron; se
        # desactiva (RN-64).
        "account_in_use",
        "journal_entry_not_found",
        # `entry_id`: ya no queda nada en «por clasificar» de ese asiento. Pasa
        # cuando dos personas miran la misma pantalla y una reclasifica primero:
        # no es un error del que llega segundo, es que ya está resuelto.
        "nothing_to_reclassify",
        # `year` y `month`: nada se escribe con fecha dentro de un periodo
        # cerrado (RN-61). Lo que haya que corregir va por un ajuste en el
        # periodo abierto.
        "period_closed",
        "period_not_found",
        # `year`, `month` y el par `blocking_*`: el mes anterior sigue abierto.
        # El saldo de un mes arranca donde terminó el anterior, así que cerrar
        # noviembre con octubre abierto congelaría un balance que todavía puede
        # cambiar por debajo (RF-52).
        "period_not_closeable",
        # Un asiento manual sin descripción. Es lo único que explica por qué
        # existe: sin ella, dentro de un año nadie sabrá qué se corrigió.
        "journal_missing_description",
        # `reason` ('both_sides', 'negative', 'empty', 'no_lines'): una línea que
        # no es ni un débito ni un crédito. **No es «no balancea»**: un asiento
        # con una línea así puede cuadrar perfectamente.
        "invalid_journal_line",
        # `debits` y `credits`: el asiento no cuadra (RN-58). Van las dos sumas
        # porque quien lo escribió necesita ver por cuánto.
        "entry_not_balanced",
        # La compañía no lleva libros, o la fecha es anterior al arranque de su
        # contabilidad (RN-60).
        "accounting_not_active",
        # -------------------------------------------------- configuración
        "unsupported_locale",
        "settings_too_large",
        "tax_rate_out_of_range",
        # La ubicación del emisor (T-722, RN-83). `field` dice cuál de los cinco
        # y `reason` qué le pasa: `required`, `unknown`, `too_short`, `too_long`.
        "invalid_location",
        # Encender la factura electrónica sin lo que el emisor necesita.
        # `missing`: la lista de `identification`, `email` y `location`.
        "einvoicing_needs_issuer",
        "settings_save_failed",
        # ------------------------------------------- factura electrónica (F6)
        # `reason` dice cuál de los cuatro motivos —`bad_pin`, `not_a_p12`,
        # `no_private_key`, `no_certificate`— porque lo que hay que hacer es
        # distinto en cada uno: volver a escribir el PIN, o ir a buscar el
        # archivo correcto.
        "invalid_certificate",
        "certificate_too_large",
        "invalid_environment",
        "atv_user_required",
        # Vault sellado, caído o sin el motor montado. Va con 503 y no con 500:
        # 503 dice «reintentá», que es exactamente el caso de alguien que
        # reinició la VM y no abrió Vault.
        "signing_unavailable",
        # ------------------------------------------------- la transmisión (F7)
        "document_not_found",
        "document_not_stopped",
        "document_not_signed",
        "document_not_resolved",
        "document_file_missing",
        "storage_unavailable",
        "production_gate_locked",
        # --------------------------- comprobar la transmisión (T-612, RF-31)
        # Los tres desenlaces de RF-31 son tres códigos y no uno con un dato
        # adentro: cada uno manda a hacer algo distinto, y el POS tiene que
        # poder decir cuál sin leer un campo.
        #
        # `atv_not_configured` es el paso previo: no hay nada que comprobar
        # todavía. No es «no sirven» —no hay nada que corregir, hay algo que
        # escribir— y por eso no se responde lo mismo.
        "atv_not_configured",
        # El IdP contestó y dijo que no. Esto sí es «no sirven».
        "atv_invalid_credentials",
        # `atv_unreachable` NO puede reportarse como el anterior (RF-31): decirle
        # a un cliente que su contraseña está mal el día que Hacienda está en
        # mantenimiento lo lleva a rotar en ATV una credencial buena, y eso no
        # es un clic. Va con 503, igual que Vault sellado, por lo mismo.
        "atv_unreachable",
        # La contraseña guardada no se pudo descifrar: la llave se rotó, o la
        # fila vino de un respaldo de otra instalación. Ni siquiera se llegó a
        # preguntarle a Hacienda, así que no es ninguno de los tres.
        "atv_password_unreadable",
        # ------------------- sucursales y terminales (T-608, RF-26, RN-15)
        # `reason` ('not_text', 'empty', 'not_digits', 'too_long') y `digits`:
        # los códigos van dentro de la clave de 50 dígitos del comprobante, en
        # posiciones fijas. El motivo viaja porque «escriba un número» no es lo
        # mismo que «ese número no cabe».
        "invalid_office_code",
        # `branch_code`: dos sucursales con el mismo código producen dos
        # facturas con la misma numeración ante Hacienda.
        #
        # El dato NO se llama `code`, por lo mismo que `account_code`: `code` es
        # el nombre del parámetro de `api_error` y pasarlo como dato choca con
        # él. Es la segunda vez que el proyecto tropieza con esto.
        "branch_code_taken",
        # `terminal_code`: por sucursal, no por compañía. Dos locales pueden
        # tener los dos su caja «00001».
        "terminal_code_taken",
        "branch_not_found",
        "terminal_not_found",
        # El arranque de una serie (T-616, RN-36 a RN-38). `value` lo que llegó;
        # `document_type` la serie que ya usó el sistema; `current` y
        # `requested`, dónde va y adónde se la quería bajar.
        "invalid_sequence_start",
        "sequence_in_use",
        "sequence_cannot_go_down",
        # `sales` y `terminals`: tiene historia o cajas colgando, así que se
        # desactiva en vez de borrarse (RN-7). Van las dos cuentas porque quien
        # lo lee necesita saber qué mover primero.
        "branch_in_use",
        # `sessions`: la caja tiene arqueos. Lo mismo.
        "terminal_in_use",
        # Queda una sola sucursal activa, o una sola caja en la sucursal:
        # desactivar la última deja a la compañía sin poder vender.
        "last_active_branch",
        "last_active_terminal",
        # ------------------------------- pasar a producción (T-611, RN-35)
        # `environment`: se pidió el cambio sin confirmarlo. Es el único sitio
        # del backend donde una confirmación es obligatoria, y está acá y no
        # solo en la pantalla porque un desplegable sin querer no puede darle
        # efecto fiscal a lo que se emita después.
        "confirmation_required",
        # -------------------------------------- tasas de planilla (T-1204)
        # `field` y `reason`: un pagador que no existe, o una carga que no es una
        # fracción —el 5,5 % es 0,055— (RN-67).
        "invalid_payroll_rate",
        # `concept`, `payer` y `latest`: una tasa no se edita, se agrega otra
        # posterior. Con la fecha de la última, para que soporte vea contra qué
        # chocó.
        "payroll_rate_not_newer",
        # `reason` e `index`: un juego de tramos de renta con un hueco, sin
        # tramo abierto al final o que no arranca en cero (T-1221). Un salario
        # que cae en el hueco no pagaría renta sin que nadie lo note.
        "invalid_tax_brackets",
        # ------------------------------------------------- planilla (F12)
        # `field` y `reason`: el número patronal, los códigos de un puesto o la
        # prima de una póliza que no tienen la forma que piden los archivos de
        # la CCSS y del INS (T-1217).
        "invalid_payroll_settings",
        # `field` y `reason`: una jornada a la que le falta o le sobra su dato
        # de corte, o con horas o días fuera de rango (RN-94).
        "invalid_schedule",
        # `resource` ('schedules' | 'positions' | 'policies') y `name`: el
        # nombre —o el número de póliza— ya está tomado en esta compañía.
        "payroll_name_taken",
        # `schedule_id`: tiene corridas pagadas, así que sus cortes no se tocan
        # (RF-83). Se crea otra jornada.
        "schedule_locked",
        "schedule_not_found",
        "position_not_found",
        "policy_not_found",
        # `field` y `reason`: un dato del empleado que la CCSS o el INS
        # rechazarían (RN-72).
        "invalid_employee",
        # `identification`: la misma persona no entra dos veces en la planilla.
        "employee_identification_taken",
        "employee_not_found",
        # `employee_id` y `terminated_on`: ya salió, o la acción es posterior a
        # su salida.
        "employee_terminated",
        # `field` y `reason`: un contrato que no se puede abrir (RN-94).
        "invalid_contract",
        # `employee_id`: no tiene contrato vigente en esa fecha; sin salario no
        # hay de qué calcular.
        "contract_missing",
        # `field` y `reason`: una acción a la que le falta o le sobra algo
        # (RN-90). La baja no entra por acá: tiene su propia ruta.
        "invalid_action",
        "action_not_found",
        # `reason` ('applied' | 'cancellation' | 'contract'): ya entró en una
        # corrida —se anula, no se edita (RN-91)—, es una anulación, o es un
        # aumento o cambio de puesto que ya movió contratos.
        "action_not_editable",
        "action_already_cancelled",
        # Suspender solo aplica a una deducción recurrente (RN-92).
        "action_not_recurring",
        "action_already_suspended",
        # `cut` y `frequency`: la fecha no es corte de esa jornada (RN-94).
        "invalid_cut_date",
        # `run_id`: ya hay una corrida de esa jornada con ese corte.
        "run_already_exists",
        "run_not_found",
        # `reason`: el estado que lo impide, o la clase de corrida que todavía
        # no se calcula (RN-68).
        "run_not_editable",
        # Aprobar un borrador sin líneas: primero se calcula.
        "run_not_calculated",
        # `status`: pagar lo que no está aprobado.
        "run_not_approved",
        "run_already_paid",
        # `missing` y `on`: a la fecha de corte falta una tasa (RN-67). Sin
        # ella la boleta saldría cobrando de menos, sin que nadie lo note.
        "rates_missing_for_date",
        # `run_id` y `status`: solo una corrida pagada se ajusta (RN-68, T-1212);
        # un borrador se recalcula.
        "run_not_paid",
        # `run_id` y `employee_id`: una liquidación de alguien que no está dado
        # de baja no tiene qué liquidar (RN-71, T-1210).
        "settlement_requires_termination",
        # `employee_id`, `balance` y `requested`: pide más días de vacaciones
        # de los que tiene (RN-70, T-1209).
        "vacation_balance_exceeded",
        # `errors`: las filas con error de una importación que pidió escribir
        # (RN-97, T-1220). Cada una trae hoja, fila y el código que daría el
        # formulario. No se escribió nada.
        "import_has_errors",
        # `missing` (empleado y campos) y `company`: lo que falta para armar el
        # archivo de la CCSS o del INS (RN-96, T-1211). No se exporta a medias.
        "export_data_incomplete",
    }
)

#: Los «sí». No los lee nadie —el POS escribe sus propios avisos de éxito— pero
#: iban en español dentro del cuerpo de la respuesta, y una respuesta con prosa
#: adentro es prosa que alguien acabará mostrando. Van como código por lo mismo
#: que los «no». El campo sigue llamándose `message` porque es el contrato que
#: ya publica el API.
DONE: frozenset[str] = frozenset(
    {
        "client_registered",
        "client_updated",
        "person_registered",
        "person_updated",
        "product_registered",
        "product_updated",
        "product_deleted",
        "cabys_assigned",
        "sale_registered",
        "return_registered",
        "entry_registered",
        "entry_cancelled",
        # F15: la salida con motivo y su anulación, y la toma física.
        "exit_registered",
        "exit_voided",
        "count_opened",
        "count_line_recorded",
        "count_applied",
        "count_discarded",
        "payment_registered",
        "role_updated",
    }
)


def api_error(status_code: int, code: str, **datos: Any) -> HTTPException:
    """Un «no» con su código y sus datos.

    Se devuelve en vez de lanzarse para que el `raise` quede a la vista en quien
    llama: `raise api_error(404, "product_not_found", product_id=7) from None`.

    El código no se valida en tiempo de ejecución a propósito. Un `assert` acá
    convertiría un error de dedo en un 500 en producción, y el guardián de
    `tests/test_error_codes.py` ya lo caza antes, leyendo el código fuente.
    """
    detail: dict[str, Any] = {"code": code}
    detail.update(datos)
    return HTTPException(status_code=status_code, detail=detail)


def unauthorized(code: str = "unauthorized", **datos: Any) -> HTTPException:
    """401 con la cabecera que pide el estándar para el esquema Bearer."""
    exc = api_error(401, code, **datos)
    exc.headers = {"WWW-Authenticate": "Bearer"}
    return exc
