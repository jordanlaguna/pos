"""Activar la contabilidad (T-1107, RF-47, RN-60).

Sin base: los repositorios son diccionarios y el libro anota. Lo que se
comprueba es lo que la activación tiene que dejar listo para que el primer día
no aparezca un saldo en rojo por algo que el sistema sabía de antemano.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pytest

from app.application.use_cases.accounting import (
    ActivateAccounting,
    ActivationRequest,
    AlreadyActive,
    OpeningLine,
    UnknownAccountCode,
    UnknownTemplate,
)
from app.domain.chart import CHART, COMMERCE, default_mapping
from app.domain.errors import EntryNotBalanced
from app.domain.ledger import OPENING
from app.domain.money import Money
from app.infrastructure.clock import FixedClock

from .fakes import FakeUnitOfWork

INICIO = date(2026, 10, 1)
AHORA = datetime(2026, 9, 30, 16, 0, 0)
ADMIN = 3


@dataclass
class FilaDeCuenta:
    id: int
    code: str
    name: str
    kind: str
    parent_id: int | None
    is_system: bool
    is_active: bool = True


class CuentasFalsas:
    def __init__(self, existentes: list[FilaDeCuenta] | None = None) -> None:
        self.cuentas = list(existentes or [])
        self._siguiente = max((c.id for c in self.cuentas), default=0) + 1

    def all(self) -> list[FilaDeCuenta]:
        return list(self.cuentas)

    def create(self, *, code, name, kind, parent_id, is_system) -> int:
        fila = FilaDeCuenta(
            self._siguiente, code, name, kind, parent_id, is_system
        )
        self.cuentas.append(fila)
        self._siguiente += 1
        return fila.id

    def por_codigo(self, code: str) -> FilaDeCuenta:
        return next(c for c in self.cuentas if c.code == code)


class MapeoFalso:
    def __init__(self) -> None:
        self.filas: dict[tuple[str, str], int] = {}

    def all(self) -> list[tuple[str, str, int]]:
        return [(evento, papel, cid) for (evento, papel), cid in self.filas.items()]

    def set(self, *, event: str, role: str, account_id: int) -> None:
        self.filas[(event, role)] = account_id


@dataclass
class FilaDePeriodo:
    id: int
    year: int
    month: int
    status: str = "open"


class PeriodosFalsos:
    def __init__(self) -> None:
        self.periodos: list[FilaDePeriodo] = []

    def get(self, year: int, month: int) -> FilaDePeriodo | None:
        return next(
            (p for p in self.periodos if p.year == year and p.month == month), None
        )

    def create(self, year: int, month: int) -> FilaDePeriodo:
        fila = FilaDePeriodo(len(self.periodos) + 1, year, month)
        self.periodos.append(fila)
        return fila


class ConfiguracionFalsa:
    def __init__(self, config: dict | None = None) -> None:
        self.config = dict(config or {})

    def accounting(self) -> dict:
        return dict(self.config)

    def save_accounting(self, config: dict) -> None:
        self.config = dict(config)


@dataclass
class DiarioFalso:
    asientos: list = field(default_factory=list)

    def post(self, entry):
        if entry is None:
            return None
        self.asientos.append(entry)
        return len(self.asientos)


@dataclass
class Mundo:
    caso: ActivateAccounting
    cuentas: CuentasFalsas
    mapeo: MapeoFalso
    periodos: PeriodosFalsos
    config: ConfiguracionFalsa
    diario: DiarioFalso
    uow: FakeUnitOfWork


@pytest.fixture
def mundo() -> Mundo:
    cuentas, mapeo = CuentasFalsas(), MapeoFalso()
    periodos, config, diario = PeriodosFalsos(), ConfiguracionFalsa(), DiarioFalso()
    uow = FakeUnitOfWork()
    return Mundo(
        caso=ActivateAccounting(
            accounts=cuentas,
            mappings=mapeo,
            periods=periodos,
            settings=config,
            journal=diario,
            uow=uow,
            clock=FixedClock(AHORA),
        ),
        cuentas=cuentas,
        mapeo=mapeo,
        periodos=periodos,
        config=config,
        diario=diario,
        uow=uow,
    )


def peticion(**cambios) -> ActivationRequest:
    datos = dict(template=COMMERCE, start_date=INICIO, user_id=ADMIN)
    datos.update(cambios)
    return ActivationRequest(**datos)


class TestLoQueSiembra:
    def test_crea_todas_las_cuentas_de_la_plantilla(self, mundo):
        resultado = mundo.caso(peticion())

        assert resultado.accounts_created == len(CHART)
        assert {c.code for c in mundo.cuentas.all()} == {p.code for p in CHART}

    def test_las_de_sistema_quedan_marcadas(self, mundo):
        # RN-64: son las que el mapeo necesita y no se pueden borrar.
        mundo.caso(peticion())

        assert mundo.cuentas.por_codigo("1.9.99").is_system
        assert not mundo.cuentas.por_codigo("6.9.02").is_system

    def test_no_falta_ninguna_fila_del_mapeo(self, mundo):
        # La verificación de T-1107. Un papel sin cuenta no rompe nada —cae en
        # 1.9.99— pero le deja al contador un saldo en rojo el primer día.
        resultado = mundo.caso(peticion())

        assert set(mundo.mapeo.filas) == set(default_mapping())
        assert resultado.mappings_created == len(default_mapping())

    def test_el_mapeo_apunta_a_la_cuenta_del_codigo_que_dice(self, mundo):
        mundo.caso(peticion())

        assert mundo.mapeo.filas[("sale", "cash")] == mundo.cuentas.por_codigo("1.1.01").id
        assert mundo.mapeo.filas[("sale", "cogs")] == mundo.cuentas.por_codigo("5.1.01").id

    def test_crea_el_periodo_de_la_fecha_de_inicio(self, mundo):
        # Los siguientes nacen solos con su primer asiento; este se crea acá
        # porque la apertura tiene que caer adentro.
        mundo.caso(peticion())

        assert [(p.year, p.month) for p in mundo.periodos.periodos] == [(2026, 10)]

    def test_si_el_periodo_ya_existia_no_lo_repite(self, mundo):
        # Puede existir: un intento anterior que falló después de crearlo, o una
        # compañía que se activa y se desactiva. El único de (compañía, año, mes)
        # rechazaría el segundo.
        mundo.periodos.create(2026, 10)
        mundo.caso(peticion())

        assert len(mundo.periodos.periodos) == 1

    def test_deja_la_configuracion_escrita(self, mundo):
        mundo.caso(peticion())

        assert mundo.config.config["active"] is True
        assert mundo.config.config["start_date"] == "2026-10-01"
        assert mundo.config.config["template"] == COMMERCE
        assert mundo.config.config["activated_by"] == ADMIN

    def test_confirma_una_sola_vez(self, mundo):
        mundo.caso(peticion())

        assert mundo.uow.committed
        assert mundo.uow.entradas == 1

    def test_lo_que_ya_existia_no_se_duplica(self, mundo):
        # Un intento anterior que falló a mitad deja cuentas escritas; volver a
        # crearlas chocaría contra el único de (compañía, código).
        mundo.cuentas.cuentas.append(
            FilaDeCuenta(1, "1.1.01", "Caja chica", "asset", None, True)
        )
        mundo.cuentas._siguiente = 2
        resultado = mundo.caso(peticion())

        assert resultado.accounts_created == len(CHART) - 1
        # Y la que ya estaba conserva su nombre: el contador pudo haberla
        # renombrado, y la activación no está para pisarle el catálogo.
        assert mundo.cuentas.por_codigo("1.1.01").name == "Caja chica"

    def test_un_papel_ya_mapeado_se_respeta(self, mundo):
        # RN-62: cambiar el mapeo afecta lo que venga, y acá no hay motivo para
        # pisarlo.
        mundo.mapeo.set(event="sale", role="cash", account_id=777)
        mundo.caso(peticion())

        assert mundo.mapeo.filas[("sale", "cash")] == 777


class TestLaApertura:
    def test_sin_saldos_iniciales_no_hay_asiento(self, mundo):
        resultado = mundo.caso(peticion())

        assert resultado.opening_entry_id is None
        assert mundo.diario.asientos == []

    def test_con_saldos_deja_un_asiento_de_apertura(self, mundo):
        resultado = mundo.caso(
            peticion(
                opening=(
                    OpeningLine("1.1.01", debit=Money(100000)),
                    OpeningLine("1.2.01", debit=Money(50000)),
                    OpeningLine("3.1.01", credit=Money(150000)),
                )
            )
        )

        assert resultado.opening_entry_id == 1
        asiento = mundo.diario.asientos[0]
        assert asiento.kind == OPENING
        assert asiento.entry_date == INICIO
        assert asiento.total == Money(150000)

    def test_las_lineas_en_blanco_se_descartan(self, mundo):
        # La pantalla ofrece más renglones de los que se usan, y una línea de
        # ceros no es una línea.
        mundo.caso(
            peticion(
                opening=(
                    OpeningLine("1.1.01", debit=Money(1000)),
                    OpeningLine("1.1.02"),
                    OpeningLine("3.1.01", credit=Money(1000)),
                )
            )
        )

        assert len(mundo.diario.asientos[0].lines) == 2

    def test_una_apertura_desbalanceada_no_entra(self, mundo):
        with pytest.raises(EntryNotBalanced):
            mundo.caso(
                peticion(
                    opening=(
                        OpeningLine("1.1.01", debit=Money(100000)),
                        OpeningLine("3.1.01", credit=Money(90000)),
                    )
                )
            )

    def test_y_entonces_no_queda_nada_activado(self, mundo):
        # Un libro no arranca descuadrado, y reintentar tiene que ser seguro.
        with pytest.raises(EntryNotBalanced):
            mundo.caso(
                peticion(opening=(OpeningLine("1.1.01", debit=Money(100000)),))
            )

        assert not mundo.uow.committed
        assert mundo.uow.rolled_back
        assert mundo.config.config == {}

    def test_una_cuenta_que_la_plantilla_no_trae(self, mundo):
        with pytest.raises(UnknownAccountCode) as fallo:
            mundo.caso(peticion(opening=(OpeningLine("9.9.99", debit=Money(1)),)))
        assert fallo.value.code == "9.9.99"

    def test_la_frase_la_escribe_quien_dicta_el_asiento(self, mundo):
        mundo.caso(
            peticion(
                description="  Saldos al 30 de setiembre  ",
                opening=(
                    OpeningLine("1.1.01", debit=Money(10)),
                    OpeningLine("3.1.01", credit=Money(10)),
                ),
            )
        )

        assert mundo.diario.asientos[0].description == "Saldos al 30 de setiembre"

    def test_sin_frase_va_el_codigo_del_evento(self, mundo):
        # El backend no escribe texto para personas (RN-30): el POS arma la
        # frase a partir del código.
        mundo.caso(
            peticion(
                opening=(
                    OpeningLine("1.1.01", debit=Money(10)),
                    OpeningLine("3.1.01", credit=Money(10)),
                )
            )
        )

        assert mundo.diario.asientos[0].description == OPENING


class TestLoQueNoSePuede:
    def test_activar_dos_veces(self, mundo):
        mundo.caso(peticion())

        with pytest.raises(AlreadyActive):
            mundo.caso(peticion())

    def test_una_plantilla_que_no_existe(self, mundo):
        with pytest.raises(UnknownTemplate) as fallo:
            mundo.caso(peticion(template="restaurante"))
        assert fallo.value.template == "restaurante"

    def test_y_no_siembra_nada(self, mundo):
        with pytest.raises(UnknownTemplate):
            mundo.caso(peticion(template="restaurante"))

        assert mundo.cuentas.all() == []
        assert not mundo.uow.committed
