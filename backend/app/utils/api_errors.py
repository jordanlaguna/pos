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
        "product_not_found",
        "product_without_price",
        "insufficient_stock",
        # `field` es 'subtotal', 'tax' o 'total': el nombre del campo en el API,
        # no la palabra de la oración.
        "totals_mismatch",
        "insufficient_payment",
        "sale_not_found",
        "sale_details_not_found",
        "sale_failed",
        # --------------------------------------------------- devoluciones
        "empty_return",
        "missing_return_reason",
        "not_sold_in_this_sale",
        "invalid_return_quantity",
        "excessive_return",
        "return_not_found",
        "return_failed",
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
        "category_name_taken",
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
        "invalid_role",
        "account_not_found",
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
        # -------------------------------------------------- configuración
        "unsupported_locale",
        "settings_too_large",
        "tax_rate_not_a_number",
        "tax_rate_out_of_range",
        "settings_save_failed",
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
