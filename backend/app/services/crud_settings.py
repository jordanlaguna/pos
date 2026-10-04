"""Configuración del negocio: moneda, impuesto, documentos, marca.

Una fila por compañía. Si no existe, se crea vacía en la primera lectura, de
modo que una compañía recién dada de alta no necesita ningún paso previo: el
frontend aplica sus valores por omisión sobre un objeto vacío y el POS arranca
funcionando.
"""

import json

from sqlalchemy.orm import Session

from app.models.model_settings import Settings
from app.utils import clock
from app.utils.api_errors import api_error
from app.utils.tenancy import compania_actual

# Tope de la configuración serializada. No es una restricción de la base (el
# campo es TEXT, 64 KB), es un cortafuegos: la configuración son unas decenas de
# campos y cualquier cosa más grande significa que algo se está usando mal.
MAX_DATA_BYTES = 20_000

# El impuesto por omisión mientras nadie lo configure. Es el IVA de Costa Rica,
# el mismo que traía fijo el WinForms.

#: Campos de la configuración que **tienen su propia puerta** y que esta no
#: puede mover (T-611).
#:
#: `save_settings` reemplaza el JSON entero con lo que manda el POS, así que sin
#: esta lista el ambiente de factura electrónica se podría cambiar por acá — y
#: entonces la confirmación y la bitácora de RN-35 serían decoración: bastaría
#: con guardar la pantalla de Configuración para pasar a producción sin que
#: quedara rastro. Es la misma frase que el proyecto ya aplica a los permisos:
#: esconder el campo no es control de acceso.
#:
#: Se guarda **lo que ya estaba**, no se rechaza la petición: el POS manda la
#: configuración completa en cada guardado y rechazarla obligaría a la pantalla
#: a conocer esta lista para no incluirlos. Ignorarlos es lo que hace que el
#: campo sea de solo lectura de verdad, venga de donde venga la petición.
PROTECTED_PATHS: tuple[tuple[str, str], ...] = (("eInvoicing", "environment"),)

#: Secciones **que escribe el backend y el POS no conoce**: la activación de la
#: contabilidad (`crud_accounting`) y los datos patronales de la planilla
#: (`crud_payroll`). Se conservan enteras al guardar, por lo mismo que los campos
#: protegidos y con un defecto detrás: la pantalla de Configuración manda solo
#: sus seis secciones, así que guardarla **borraba** `accounting` y la
#: contabilidad quedaba desactivada en silencio —el libro dejaba de recibir
#: asientos sin un solo error— (defecto corregido el 2026-10-02, sesión 76). Cada una tiene su
#: propia puerta y su propia bitácora; esta no las toca ni para ponerlas ni para
#: quitarlas.
OWNED_SECTIONS: tuple[str, ...] = ("accounting", "payroll")


def _conservar_protegidos(nuevo: dict, anterior: dict) -> dict:
    """Devuelve `nuevo` con los campos protegidos y las secciones del backend
    como estaban en `anterior`.

    Un campo que no existía sigue sin existir: si nadie eligió ambiente todavía,
    esto no inventa uno. Y una sección del backend que venga en la petición se
    ignora: no es de quien guarda la pantalla.
    """
    for seccion in OWNED_SECTIONS:
        if seccion in anterior:
            nuevo[seccion] = anterior[seccion]
        else:
            nuevo.pop(seccion, None)

    for contenedor, campo in PROTECTED_PATHS:
        vieja = anterior.get(contenedor)
        guardado = vieja.get(campo) if isinstance(vieja, dict) else None

        seccion = nuevo.get(contenedor)
        if not isinstance(seccion, dict):
            if guardado is None:
                continue
            seccion = {}
            nuevo[contenedor] = seccion

        if guardado is None:
            seccion.pop(campo, None)
        else:
            seccion[campo] = guardado
    return nuevo


def _row(db: Session) -> Settings:
    """La fila de ESTA compañía.

    Antes era `WHERE id = 1`, y con una sola compañía eso era exacto. Ahora el
    `WHERE company_id` lo pone el filtro automático, así que la consulta no
    lleva condición: pedir «la configuración» ya significa «la de la compañía
    de esta petición».
    """
    row = db.query(Settings).first()
    if row is None:
        row = Settings(company_id=compania_actual(), data="{}")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _parse(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        # Fila corrupta: se devuelve vacía y el frontend aplica sus valores por
        # omisión. Vale más un POS con la moneda de fábrica que uno que no abre.
        return {}
    return value if isinstance(value, dict) else {}


def sin_impuesto(data: dict) -> dict:
    """La configuración sin impuesto (QA-05).

    El impuesto ya no se configura: la tarifa de cada producto es la de su
    CABYS y, sin ella, la general del IVA (`domain.tax.GENERAL_RATE`). Lo que
    llegue como `tax` —o `impuesto`, la forma de antes de T-113— se descarta al
    guardar, para que la fila no siga diciendo una tasa que nadie usa y que el
    día de mañana alguien crea que manda.
    """
    return {k: v for k, v in data.items() if k not in ("tax", "impuesto")}


def _emisor(db: Session) -> dict:
    """La identificación del emisor: la de `companies`, no la de la configuración.

    RN-45: la fija soporte y el negocio la ve sin poder editarla, porque el
    certificado se emite a ella. Viaja con la configuración para que la
    pantalla la muestre y las plantillas impriman **la misma** que va dentro de
    la clave. El tipo, si soporte no lo cargó, es el que deja ver la cédula.
    """
    from app.domain.hacienda import identification_type_for
    from app.models.model_company import Company

    company = db.get(Company, compania_actual())
    identificacion = (company.identificacion or "").strip() if company else ""
    tipo = company.identification_type if company else None
    return {
        "identification": identificacion or None,
        "identification_type": tipo or (identification_type_for(identificacion) if identificacion else None),
    }


def get_settings(db: Session) -> dict:
    row = _row(db)
    logo = None
    if row.logo_data and row.logo_mime:
        logo = {"mime": row.logo_mime, "data": row.logo_data}

    return {
        "data": _parse(row.data),
        "logo": logo,
        "updated_at": row.updated_at,
        "updated_by": row.updated_by,
        "issuer": _emisor(db),
    }


def _validar_emisor(db: Session, data: dict) -> None:
    """La ubicación, si viene, y lo que hace falta para emitir, si se enciende.

    Son dos reglas (T-722, RN-83):

    * **Una ubicación a medias no se guarda**, emita o no la compañía: es un
      error de quien escribe y hay que decirle cuál campo falta. Una vacía sí,
      porque quien no emite no tiene por qué dar su distrito.
    * **La factura electrónica no se enciende sin emisor**: cédula, correo y
      ubicación. Se dice todo lo que falta de una vez.

    Se revisa al guardar y no al vender: rechazar la venta le cobra el problema
    al cliente que está en el mostrador.
    """
    from app.domain.errors import EInvoicingNeedsIssuer, InvalidLocation
    from app.domain.fe_issuer import check_ready_to_emit
    from app.domain.locations import is_blank, location_from_settings
    from app.models.model_company import Company

    negocio = data["business"] if "business" in data else data.get("negocio")
    negocio = negocio if isinstance(negocio, dict) else {}
    ubicacion = negocio.get("location")
    if not is_blank(ubicacion):
        try:
            location_from_settings(ubicacion)
        except InvalidLocation as e:
            raise api_error(400, "invalid_location", field=e.field, reason=e.reason) from None

    seccion = data["eInvoicing"] if "eInvoicing" in data else data.get("electronica")
    seccion = seccion if isinstance(seccion, dict) else {}
    encendida = (seccion["enabled"] if "enabled" in seccion else seccion.get("activa")) is True
    if not encendida:
        return

    company = db.get(Company, compania_actual())
    correo = negocio["email"] if "email" in negocio else negocio.get("correo")
    try:
        check_ready_to_emit(
            identification=company.identificacion if company else None,
            email=correo,
            location=ubicacion,
        )
    except EInvoicingNeedsIssuer as e:
        raise api_error(400, "einvoicing_needs_issuer", missing=list(e.missing)) from None


def save_settings(
    db: Session,
    data: dict,
    logo: dict | None,
    keep_logo: bool,
    user_id: int,
) -> dict:
    # Lo protegido se restaura ANTES de medir el tamaño y de validar: lo que se
    # mide tiene que ser lo que se va a guardar.
    row = _row(db)
    data = sin_impuesto(_conservar_protegidos(dict(data), _parse(row.data)))

    serialized = json.dumps(data, ensure_ascii=False)
    if len(serialized.encode("utf-8")) > MAX_DATA_BYTES:
        raise api_error(400, "settings_too_large", max_bytes=MAX_DATA_BYTES)

    _validar_emisor(db, data)

    try:
        row.data = serialized
        if logo is not None:
            row.logo_mime = logo["mime"]
            row.logo_data = logo["data"]
        elif not keep_logo:
            row.logo_mime = None
            row.logo_data = None
        row.updated_at = clock.now()
        row.updated_by = user_id
        db.commit()
        db.refresh(row)
    except Exception as exc:
        db.rollback()
        raise api_error(500, "settings_save_failed", cause=str(exc))

    return get_settings(db)


def read_protected(db: Session, contenedor: str, campo: str) -> object | None:
    """Lo que hay guardado en un campo protegido, sin valor por omisión.

    Devuelve `None` cuando nadie lo ha elegido nunca, y decidir qué significa
    eso es de quien pregunta: para el ambiente significa «pruebas» (`crud_fe`),
    y suponer lo contrario sería suponer efecto fiscal donde no lo hay.
    """
    seccion = _parse(_row(db).data).get(contenedor)
    return seccion.get(campo) if isinstance(seccion, dict) else None


def write_protected(db: Session, contenedor: str, campo: str, valor: object) -> None:
    """La **única** puerta que escribe un campo protegido. No confirma.

    No hace `commit` a propósito: quien la llama tiene que poder meter en la
    misma transacción la anotación de bitácora que explica el cambio. Un campo
    que se cambia por su puerta auditada y se confirma aparte podría quedar
    cambiado sin su línea de bitácora, que es la mitad de lo que RN-35 pide.

    Exige que el campo **esté** en `PROTECTED_PATHS`: si alguien lo saca de la
    lista, esto deja de funcionar en vez de convertirse en una segunda forma
    silenciosa de escribir la configuración.
    """
    if (contenedor, campo) not in PROTECTED_PATHS:
        raise ValueError(f"«{contenedor}.{campo}» no es un campo protegido")

    row = _row(db)
    data = _parse(row.data)
    seccion = data.get(contenedor)
    if not isinstance(seccion, dict):
        seccion = {}
        data[contenedor] = seccion
    seccion[campo] = valor
    row.data = json.dumps(data, ensure_ascii=False)
    row.updated_at = clock.now()


def get_einvoicing_enabled(db: Session) -> bool:
    """Si la compañía factura electrónicamente (RN-85).

    Lee lo mismo que `mergeSettings` en el POS —`eInvoicing.enabled`, y la forma
    de antes, `electronica.activa`— y con la misma regla: **solo un booleano de
    verdad cuenta**. Si el servidor leyera un `"true"` escrito a mano y la
    pantalla no, la caja cobraría tiquetes que el documento no anuncia.

    Apagada por omisión, que es como nace toda compañía.
    """
    seccion = _seccion_electronica(db)
    if seccion is None:
        return False
    valor = seccion["enabled"] if "enabled" in seccion else seccion.get("activa")
    return valor is True


def get_document_types(db: Session) -> frozenset[str]:
    """Los comprobantes que emite la compañía, saneados (RN-88).

    El saneo es del dominio (`enabled_types`) y es el mismo que aplica el POS al
    leer la configuración: lo que la pantalla muestra encendido es lo que el
    servidor deja emitir.
    """
    from app.domain.fe_document_type import enabled_types

    seccion = _seccion_electronica(db)
    return enabled_types(seccion.get("documentTypes") if seccion else None)


def _seccion_electronica(db: Session) -> dict | None:
    """La sección de factura electrónica, venga con el nombre que venga.

    Como `legacy()` del POS: manda la clave nueva si **está**, aunque no sirva.
    """
    data = _parse(_row(db).data)
    seccion = data["eInvoicing"] if "eInvoicing" in data else data.get("electronica")
    return seccion if isinstance(seccion, dict) else None


def get_einvoicing_environment(db: Session) -> str:
    """El ambiente en uso: `sandbox` si nadie eligió o lo guardado no se entiende.

    Cae al inofensivo, como `crud_fe._activo`: suponer producción sería suponer
    efecto fiscal donde no lo hay.
    """
    from app.domain.errors import InvalidEnvironment
    from app.domain.hacienda import SANDBOX, check_environment

    try:
        return check_environment(read_protected(db, "eInvoicing", "environment"))
    except InvalidEnvironment:
        return SANDBOX


def get_economic_activity(db: Session) -> str | None:
    """La actividad económica configurada, o nula. Se congela en cada comprobante."""
    seccion = _seccion_electronica(db)
    if seccion is None:
        return None
    valor = seccion["economicActivity"] if "economicActivity" in seccion else seccion.get("actividad_economica")
    if not isinstance(valor, str):
        return None
    return valor.strip() or None
