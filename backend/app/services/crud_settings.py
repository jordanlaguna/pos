"""Configuración del negocio: moneda, impuesto, documentos, marca.

Una fila por compañía. Si no existe, se crea vacía en la primera lectura, de
modo que una compañía recién dada de alta no necesita ningún paso previo: el
frontend aplica sus valores por omisión sobre un objeto vacío y el POS arranca
funcionando.
"""

import json
from decimal import Decimal

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
DEFAULT_TAX_RATE = Decimal("0.13")

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


def _conservar_protegidos(nuevo: dict, anterior: dict) -> dict:
    """Devuelve `nuevo` con los campos protegidos como estaban en `anterior`.

    Un campo que no existía sigue sin existir: si nadie eligió ambiente todavía,
    esto no inventa uno.
    """
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


def tasa_declarada(data: dict) -> tuple[str, object] | None:
    """Dónde y con qué valor viene la tasa, venga en la forma que venga.

    Son dos: `tax.rate` desde T-113 y el `impuesto.tasa` de antes. Una fila
    guardada con la versión anterior tiene que seguir entendiéndose; si no,
    actualizar el sistema haría que el POS cobrara con la tasa de fábrica sin
    decir nada.

    Existe como función porque los dos sitios que la leen —el que **valida** al
    guardar y el que **calcula** al cobrar— tienen que mirar el mismo campo. Ya
    no lo hacían: la validación leía solo la forma vieja mientras el POS escribía
    la nueva, así que una tasa fuera de rango no levantaba `tax_rate_out_of_range`
    y se la tragaba el respaldo de `get_tax_rate`. El dueño configuraba 500 %, la
    pantalla se lo mostraba y el servidor cobraba 13 %, sin un solo error.
    """
    for contenedor, campo in (("tax", "rate"), ("impuesto", "tasa")):
        seccion = data.get(contenedor)
        if isinstance(seccion, dict) and seccion.get(campo) is not None:
            return f"{contenedor}.{campo}", seccion[campo]
    return None


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
    }


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
    data = _conservar_protegidos(dict(data), _parse(row.data))

    serialized = json.dumps(data, ensure_ascii=False)
    if len(serialized.encode("utf-8")) > MAX_DATA_BYTES:
        raise api_error(400, "settings_too_large", max_bytes=MAX_DATA_BYTES)

    # Único campo que este backend lee por su cuenta (crud_return lo usa para
    # calcular el reembolso), así que es el único que valida aquí. Se busca con
    # `tasa_declarada`, el mismo lector que usa `get_tax_rate`: si la validación
    # mirara un campo y el cálculo otro, una tasa mala pasaría el control y se
    # perdería después en el respaldo, en silencio.
    declarada = tasa_declarada(data)
    if declarada is not None:
        _, valor = declarada
        try:
            rate = Decimal(str(valor))
        except Exception:
            raise api_error(400, "tax_rate_not_a_number", value=str(valor)) from None
        if rate < 0 or rate > 1:
            raise api_error(400, "tax_rate_out_of_range", value=float(rate))

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


def get_tax_rate(db: Session) -> Decimal:
    """Tasa de impuesto configurada, para quien la necesite del lado del servidor.

    Devuelve la de Costa Rica mientras nadie configure otra. Cualquier valor
    fuera de rango se ignora en vez de propagarse a un cálculo de plata.
    """
    try:
        declarada = tasa_declarada(_parse(_row(db).data))
        if declarada is None:
            return DEFAULT_TAX_RATE
        rate = Decimal(str(declarada[1]))
        # El respaldo sigue acá porque una fila puede venir de antes de que
        # `save_settings` validara las dos formas, o escrita a mano. Lo que ya no
        # puede pasar es que este respaldo tape una tasa que el POS acaba de
        # guardar: eso ahora se rechaza al guardarla.
        return rate if 0 <= rate <= 1 else DEFAULT_TAX_RATE
    except Exception:
        return DEFAULT_TAX_RATE
