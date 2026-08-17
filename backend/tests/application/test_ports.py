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

from app.application.ports import clock, repositories, security

PUERTOS = [
    (clock.Clock, {"now", "today"}),
    (
        repositories.ProductRepository,
        {
            "get",
            "get_by_barcode",
            "lock_for_sale",
            "adjust_stock",
            "barcode_taken",
            "create",
        },
    ),
    (
        repositories.StockEntryRepository,
        {"get", "applied_with_document", "add", "lines_of", "mark_cancelled"},
    ),
    (
        repositories.SaleRepository,
        {"add", "get", "exists_with_number", "sold_quantities", "sold_prices", "in_window"},
    ),
    (repositories.ReturnRepository, {"returned_quantities", "add", "total_in_window"}),
    (repositories.SettingsRepository, {"tax_rate"}),
    (
        repositories.CashRepository,
        {"open_session", "create_session", "close_session", "add_movement", "movements"},
    ),
    (repositories.UnitOfWork, {"__enter__", "__exit__", "commit", "rollback"}),
    (security.PasswordHasher, {"hash", "verify"}),
    (security.TokenIssuer, {"issue", "read"}),
    (repositories.ProductSnapshot, set()),
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

    for modulo in (clock, repositories, security):
        fuente = inspect.getsource(modulo)
        for prohibido in ("sqlalchemy", "fastapi", "pydantic", "app.models"):
            assert prohibido not in fuente, f"{modulo.__name__} importa {prohibido}"
