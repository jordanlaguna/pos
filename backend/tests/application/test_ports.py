"""
Los puertos son un contrato, y un contrato se comprueba.

Estas pruebas no ejercitan lógica —los puertos no tienen— sino que fijan **qué
métodos promete cada uno**. Sirven para dos cosas: que renombrar un método de un
puerto sin actualizar a quien lo implementa se note acá y no en producción, y
que la carpeta entre en la cuenta del 100 % en vez de quedar como un hueco
silencioso.

También comprueban lo que hace que esta arquitectura funcione: que sean
`Protocol`, o sea que cumplirlos no exija heredar nada. Si un puerto dejara de
serlo, el adaptador tendría que importar la capa de aplicación y la dependencia
apuntaría hacia afuera.
"""

from __future__ import annotations

from typing import Protocol, get_type_hints

import pytest

from app.application.ports import (
    clock,
    documents,
    fe_documents,
    numbering,
    payroll,
    repositories,
    secrets,
    security,
    signing,
    transmission,
)

PUERTOS = [
    (clock.Clock, {"now", "today"}),
    (
        repositories.ProductRepository,
        {
            "get",
            "get_by_barcode",
            "lock_for_sale",
            "adjust_stock",
            # Desde F10: el promedio ponderado lo calcula el dominio y acá solo
            # se guarda (RN-54).
            "update_cost",
            "barcode_taken",
            "create",
        },
    ),
    (repositories.SupplierRepository, {"get"}),
    (
        repositories.StockEntryRepository,
        {"get", "applied_with_document", "add", "lines_of", "mark_cancelled"},
    ),
    (
        repositories.SaleRepository,
        {
            "add",
            "get",
            "exists_with_number",
            "sold_quantities",
            "sold_prices",
            # Desde F5: la tarifa congelada de cada línea, que es lo que
            # impide que una devolución parcial use el promedio de la venta.
            "sold_tax_rates",
            # Desde F11: el costo congelado, que es lo que hace que devolver
            # mercadería la reponga por lo que costó y no por lo que cuesta hoy.
            "sold_costs",
            "in_window",
        },
    ),
    (repositories.ReturnRepository, {"returned_quantities", "add", "total_in_window"}),
    # T-726: las notas por monto. Lo que cambiaron en cada línea —lo piden la NC
    # y la devolución—, guardarlas, y las del turno para el arqueo.
    (repositories.NoteRepository, {"adjustments", "add", "in_window"}),
    # Desde F7: si la compañía factura electrónicamente, que es lo que decide si
    # la venta lleva tipo de comprobante (RN-85).
    (repositories.SettingsRepository, {"einvoicing_enabled", "document_types"}),
    # F7: el receptor de la venta tiene que ser de la compañía, y desde T-727
    # la venta necesita saber quién es ante Hacienda: al del extranjero se le
    # exporta. Una sola pregunta, que devuelve eso.
    (repositories.ClientRepository, {"get"}),
    (
        repositories.CashRepository,
        {"open_session", "create_session", "close_session", "add_movement", "movements"},
    ),
    (repositories.UnitOfWork, {"__enter__", "__exit__", "commit", "rollback"}),
    (security.PasswordHasher, {"hash", "verify"}),
    (security.TokenIssuer, {"issue", "read"}),
    # F6: el almacén de comprobantes. Sin `delete` a propósito —estos
    # documentos se custodian por ley y borrarlos es mantenimiento, no una
    # operación de la aplicación—; un método acá sería una invitación.
    (documents.DocumentStore, {"put", "get", "exists"}),
    # F6: quién firma. `forget_key` no estaba en el boceto del plan y hace falta
    # para RF-24: sin él, quitar el certificado dejaría la fila vacía y la llave
    # viva en Vault —el negocio creería que no puede firmar y el sistema podría
    # hacerlo—.
    (signing.DocumentSigner, {"import_key", "sign", "forget_key"}),
    # F6: el cifrado en reposo, con un solo cliente —la contraseña de ATV—.
    # Todo lo demás que era secreto se fue a Vault, donde no se guarda nada que
    # se pueda leer de vuelta.
    (secrets.SecretBox, {"encrypt", "decrypt"}),
    # F6: quién le pide el token a Hacienda. Un solo método, y devuelve el token
    # aunque T-612 lo tire: F7 lo necesita para transmitir, y un puerto que
    # devolviera `bool` habría que cambiarlo entonces.
    (transmission.HaciendaIdp, {"token"}),
    # F7: la otra mitad de hablar con Hacienda (T-708, T-709): entregar el XML y
    # preguntar qué decidió. Dos métodos y no uno por recurso: son los dos del
    # README §7, y el resto —el 202, el 404, el token vencido— son excepciones.
    (transmission.HaciendaReception, {"submit", "status"}),
    # F7: lo que la firma necesita del certificado público (T-712). Aparte de
    # `CertificateReader`, que abre el `.p12` y se olvida de él.
    (signing.CertificateParser, {"facts"}),
    # F7: el recorrido (T-707 a T-713). El repositorio es ancho a propósito: la
    # cola, la pantalla, la contingencia y la puerta de producción leen lo
    # mismo, y partirlo en cuatro sería cuatro adaptadores sobre una tabla.
    (
        fe_documents.TransmissionRepository,
        {
            "get",
            "latest_for",
            "due",
            "update",
            "add_event",
            "events",
            "health",
            "stopped",
            "counts",
            "accepted_by_type",
        },
    ),
    (fe_documents.ComprobanteSource, {"comprobante"}),
    (fe_documents.ContingencyMode, {"active"}),
    # F7: la numeración (T-704, T-705). Tres puertos porque son tres razones de
    # cambio: quién emite, el contador con su bloqueo, y el azar de la clave.
    (numbering.IssuerRepository, {"issuer"}),
    (
        numbering.DocumentNumbering,
        {"office", "last_sequence", "save_sequence", "record"},
    ),
    (numbering.SecurityCodes, {"new"}),
    # F12: la planilla (T-1205, T-1206, T-1218, T-1209, T-1210). Nueve puertos
    # por nueve razones de cambio; el libro es el de F11.
    (payroll.ScheduleRepository, {"get"}),
    (
        payroll.EmployeeRepository,
        {
            "get",
            "contracts_of",
            "contracts_in",
            "contracts_between",
            "add_contract",
            "close_contract",
            "terminate",
            "position_active",
            "rt_rate",
        },
    ),
    (payroll.ActionRepository, {"get", "for_employee", "add", "update", "suspend", "applied"}),
    (
        payroll.PayrollRepository,
        {
            "get_run",
            "find_run",
            "add_run",
            "line_count",
            "lines",
            "replace_lines",
            "totals",
            "paid_earnings",
            "month_withholding",
            "approve",
            "pay",
        },
    ),
    (payroll.RateTable, {"rates", "brackets_at", "credits_at", "severance_at"}),
    (payroll.PayrollSettings, {"payroll"}),
    # Las vacaciones son una suma de movimientos (RN-70) y lo de apertura son
    # meses (RN-97): cada uno con su puerta, porque los importa T-1220 aparte.
    (payroll.VacationRepository, {"movements", "add", "update_for_action"}),
    (payroll.OpeningRepository, {"earnings", "add_earning"}),
    # Los archivos del mes (T-1211, T-1219) leen un mes pagado ya armado.
    (payroll.PayrollReports, {"month", "employer", "policy_number"}),
    # La importación (T-1220) busca por nombre lo que el formulario busca por id.
    (
        payroll.ImportRepository,
        {
            "position_by_name",
            "add_position",
            "schedule_by_name",
            "policy_by_number",
            "employee_by_identification",
            "add_employee",
        },
    ),
    (repositories.ProductSnapshot, set()),
    (repositories.SupplierSnapshot, set()),
    (repositories.ClientSnapshot, set()),
    (payroll.ScheduleSnapshot, set()),
    (payroll.EmployeeSnapshot, set()),
    (payroll.ContractSnapshot, set()),
    (payroll.ActionSnapshot, set()),
    (payroll.AppliedItem, set()),
    (payroll.RunSnapshot, set()),
    (payroll.VacationSnapshot, set()),
]


def metodos(puerto) -> set[str]:
    """Los métodos que declara el puerto, sin los que trae Protocol de fábrica."""
    heredados = set(dir(Protocol)) | {"_is_protocol", "_is_runtime_protocol"}
    return {
        nombre
        for nombre in vars(puerto)
        if callable(getattr(puerto, nombre, None)) and nombre not in heredados
    }


@pytest.mark.parametrize("puerto, esperados", PUERTOS, ids=lambda x: getattr(x, "__name__", ""))
def test_cada_puerto_declara_lo_que_promete(puerto, esperados):
    assert metodos(puerto) == esperados


@pytest.mark.parametrize("puerto", [p for p, _ in PUERTOS], ids=lambda p: p.__name__)
def test_todos_son_Protocol(puerto):
    # Es lo que permite que un repositorio de SQLAlchemy los cumpla sin importar
    # esta capa. Con una clase base, la dependencia apuntaría hacia afuera.
    assert getattr(puerto, "_is_protocol", False), f"{puerto.__name__} dejó de ser Protocol"


def test_ProductSnapshot_dice_que_necesita_la_venta_de_un_producto():
    # No tiene métodos: es la forma de los datos, no un comportamiento.
    assert set(get_type_hints(repositories.ProductSnapshot)) == {
        "id_product",
        "name",
        "price",
        "stock",
        # Desde F5: la tarifa del producto, o `None` si usa la configurada.
        "tax_rate",
        # Desde F7: el código de tarifa de Hacienda. No se deduce de `tax_rate`
        # —once códigos para nueve porcentajes— y por eso viaja aparte (RN-76).
        "tax_code",
        # Desde F10: lo que cuesta, que no es lo que vale. Cero es «no se sabe»
        # —los productos que nunca se compraron— y la primera compra lo fija.
        "cost",
        # Desde F7 (T-731): el CABYS y la unidad, que se congelan en la línea
        # porque el comprobante los imprime y el producto puede cambiarlos.
        "cabys_code",
        "unit_of_measure",
        # Desde T-727: la partida arancelaria, que la factura de exportación
        # exige en cada mercancía.
        "tariff_heading",
    }


def test_ClientSnapshot_dice_quien_es_el_receptor_ante_hacienda():
    # Ni nombre ni correo: la venta guarda el id y el comprobante los lee
    # después. Lo que decide al vender es el tipo de identificación (RN-87).
    assert set(get_type_hints(repositories.ClientSnapshot)) == {
        "id_client",
        "identification_type",
        "foreign_address",
    }


def test_SupplierSnapshot_dice_lo_justo_para_comprarle():
    # Ni correo ni teléfono: para registrar una compra no hacen falta, y un
    # puerto que pide de más ata la aplicación a datos que no usa.
    assert set(get_type_hints(repositories.SupplierSnapshot)) == {
        "id",
        "name",
        "is_active",
        "payment_terms_days",
        # Desde T-728: a un no contribuyente se le emite la factura de compra,
        # y él es su emisor: sin cédula no se numera.
        "identification_type",
        "identification",
    }


def test_los_puertos_no_conocen_la_persistencia_ni_HTTP():
    """
    La regla de dependencias, comprobada donde más barato sale.

    T-114 la verifica en todo el proyecto; acá se adelanta para los puertos,
    que son justo donde la tentación es mayor: es cómodo escribir que un
    repositorio devuelve un `Sale` de SQLAlchemy, y con eso la aplicación queda
    atada a la base para siempre.
    """
    import inspect

    for modulo in (
        clock,
        documents,
        fe_documents,
        payroll,
        repositories,
        secrets,
        security,
        signing,
        transmission,
    ):
        fuente = inspect.getsource(modulo)
        for prohibido in ("sqlalchemy", "fastapi", "pydantic", "app.models"):
            assert prohibido not in fuente, f"{modulo.__name__} importa {prohibido}"
