"""Los datos de contabilidad en SQLAlchemy (T-1107).

Adaptadores de `ports/accounting.py`. Ninguno confirma: escriben en la sesión que
les pasan y el `commit` lo da quien abrió la unidad de trabajo, igual que el
resto de los repositorios.

El `company_id` no se escribe en ninguna parte y no es un olvido: lo pone el
escuchador de `before_flush` (plan §3.3), el mismo que lo pone en una venta.
"""

from __future__ import annotations

import json

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain.money import Money
from app.domain.ledger import Line
from app.domain.tax import TaxRate
from app.models.model_accounting import Account, AccountingPeriod, AccountMapping
from app.models.model_accounting import JournalEntry as FilaDeAsiento
from app.models.model_accounting import JournalLine as FilaDeLinea
from app.models.model_settings import Settings
from app.utils.tenancy import compania_actual


class SqlAlchemyAccountRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def all(self) -> list[Account]:
        return self._db.query(Account).order_by(Account.code).all()

    def by_code(self, code: str) -> Account | None:
        return self._db.query(Account).filter(Account.code == code).first()

    def get(self, account_id: int) -> Account | None:
        return self._db.query(Account).filter(Account.id == account_id).first()

    def create(
        self,
        *,
        code: str,
        name: str,
        kind: str,
        parent_id: int | None,
        is_system: bool,
    ) -> int:
        cuenta = Account(
            code=code,
            name=name,
            kind=kind,
            parent_id=parent_id,
            is_system=is_system,
            is_active=True,
        )
        self._db.add(cuenta)
        self._db.flush()
        return cuenta.id

    def lines_for(self, account_id: int) -> int:
        """Cuántas líneas de asiento tocan esa cuenta.

        El `company_id` va escrito a mano: `func.count` envuelve la consulta en
        una subconsulta donde el filtro automático no entra (plan §3.3), y sin él
        una cuenta sin movimiento propio se vería en uso por los asientos de otra
        compañía —y no se podría borrar nunca—.
        """
        return int(
            self._db.query(func.count(FilaDeLinea.id))
            .filter(
                FilaDeLinea.account_id == account_id,
                FilaDeLinea.company_id == compania_actual(),
            )
            .scalar()
            or 0
        )

    def update(self, cuenta: Account, *, name: str | None, is_active: bool | None) -> Account:
        """Renombrar y activar o desactivar. El código **no** se cambia.

        El código es lo que el contador usa para referirse a la cuenta en papel y
        lo que ordena el catálogo; cambiarlo dejaría los reportes ya impresos
        hablando de otra cuenta. Se borra y se crea, que es lo que de verdad pasó.
        """
        if name is not None:
            cuenta.name = name
        if is_active is not None:
            cuenta.is_active = is_active
        self._db.flush()
        return cuenta

    def delete(self, cuenta: Account) -> None:
        self._db.delete(cuenta)
        self._db.flush()


class SqlAlchemyMappingRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def all(self) -> list[tuple[str, str, int]]:
        return [
            (fila.event, fila.role, fila.account_id)
            for fila in self._db.query(AccountMapping).all()
        ]

    def set(self, *, event: str, role: str, account_id: int) -> None:
        fila = (
            self._db.query(AccountMapping)
            .filter(AccountMapping.event == event, AccountMapping.role == role)
            .first()
        )
        if fila is None:
            self._db.add(AccountMapping(event=event, role=role, account_id=account_id))
        else:
            # Cambiar el mapeo afecta lo que venga, nunca lo que ya está en el
            # libro (RN-62): los asientos guardaron el id de cuenta, no el papel.
            fila.account_id = account_id
        self._db.flush()


class SqlAlchemyPeriodRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, year: int, month: int) -> AccountingPeriod | None:
        return (
            self._db.query(AccountingPeriod)
            .filter(AccountingPeriod.year == year, AccountingPeriod.month == month)
            .first()
        )

    def all(self) -> list[AccountingPeriod]:
        return (
            self._db.query(AccountingPeriod)
            .order_by(AccountingPeriod.year.desc(), AccountingPeriod.month.desc())
            .all()
        )

    def create(self, year: int, month: int) -> AccountingPeriod:
        periodo = AccountingPeriod(year=year, month=month, status="open")
        self._db.add(periodo)
        self._db.flush()
        return periodo

    def close(self, periodo: AccountingPeriod, *, closed_at, closed_by: int) -> AccountingPeriod:
        """Lo cierra. **No hay `reopen`**, y esa ausencia es la regla (RN-61)."""
        periodo.status = "closed"
        periodo.closed_at = closed_at
        periodo.closed_by = closed_by
        self._db.flush()
        return periodo

    def any_closed_after(self, year: int, month: int) -> bool:
        """Si hay algún mes **posterior** ya cerrado.

        Es el agujero que dejaría RN-61 sin esto: cerrar setiembre no impide
        escribir en agosto **si agosto nunca tuvo un asiento**, porque entonces no
        tiene fila y nace abierto. Sin esta comprobación, una factura vieja
        capturada tarde cambiaría un balance ya entregado.

        El `company_id` no hace falta escribirlo: es una consulta del ORM sobre
        una tabla de negocio, así que el filtro automático entra.
        """
        return (
            self._db.query(AccountingPeriod)
            .filter(
                AccountingPeriod.status == "closed",
                (AccountingPeriod.year > year)
                | ((AccountingPeriod.year == year) & (AccountingPeriod.month > month)),
            )
            .first()
            is not None
        )


class SqlAlchemyAccountingSettings:
    """La sección `accounting` del JSON de configuración.

    Escribe con `db.flush()` y no con el `save_settings` de `crud_settings`, que
    confirma: la activación tiene que entrar completa o no entrar, y una
    configuración que dice «activa» sobre un catálogo a medias es peor que no
    haber activado.
    """

    SECCION = "accounting"

    def __init__(self, db: Session) -> None:
        self._db = db

    def _fila(self) -> Settings:
        fila = self._db.query(Settings).first()
        if fila is None:
            # Una compañía a la que nadie le ha guardado configuración todavía.
            # Se crea vacía, sin confirmar: si la activación falla después, esta
            # fila se va con ella.
            fila = Settings(company_id=compania_actual(), data="{}")
            self._db.add(fila)
            self._db.flush()
        return fila

    def _datos(self, fila: Settings) -> dict:
        try:
            datos = json.loads(fila.data or "{}")
        except (TypeError, ValueError):
            return {}
        return datos if isinstance(datos, dict) else {}

    def accounting(self) -> dict:
        seccion = self._datos(self._fila()).get(self.SECCION)
        return seccion if isinstance(seccion, dict) else {}

    def save_accounting(self, config: dict) -> None:
        fila = self._fila()
        datos = self._datos(fila)
        datos[self.SECCION] = config
        fila.data = json.dumps(datos, ensure_ascii=False)
        self._db.flush()


class SqlAlchemyJournalRepository:
    """Los asientos, para leerlos.

    Devuelve `Line` del dominio y no filas de SQLAlchemy porque quien las usa es
    una función pura —la reclasificación—, y darle filas la ataría a la base.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, entry_id: int) -> FilaDeAsiento | None:
        return self._db.query(FilaDeAsiento).filter(FilaDeAsiento.id == entry_id).first()

    def en_el_mes(
        self, *, year: int | None = None, month: int | None = None, kind: str | None = None
    ) -> list[FilaDeAsiento]:
        """El libro diario: por fecha y, dentro del día, por correlativo.

        Sin mes devuelve todo lo del año; sin año, todo. Es el mismo orden en que
        se imprime un diario, y el correlativo desempata porque dos asientos del
        mismo día tienen que salir siempre en el mismo orden.
        """
        consulta = self._db.query(FilaDeAsiento)
        if year is not None:
            consulta = consulta.filter(func.year(FilaDeAsiento.entry_date) == year)
        if month is not None:
            consulta = consulta.filter(func.month(FilaDeAsiento.entry_date) == month)
        if kind:
            consulta = consulta.filter(FilaDeAsiento.kind == kind)
        return consulta.order_by(FilaDeAsiento.entry_date, FilaDeAsiento.entry_number).all()

    def filas_con_cuenta(self, entry_id: int) -> list[tuple[FilaDeLinea, Account]]:
        """Las líneas con su cuenta, para mostrarlas."""
        return (
            self._db.query(FilaDeLinea, Account)
            .join(Account, Account.id == FilaDeLinea.account_id)
            .filter(FilaDeLinea.entry_id == entry_id)
            .order_by(FilaDeLinea.id)
            .all()
        )

    def lines_of(self, entry_id: int) -> list[Line]:
        filas = (
            self._db.query(FilaDeLinea)
            .filter(FilaDeLinea.entry_id == entry_id)
            .order_by(FilaDeLinea.id)
            .all()
        )
        return [
            Line(
                account_id=fila.account_id,
                debit=Money(fila.debit),
                credit=Money(fila.credit),
                # De porcentaje a tasa: en la base va 13 y el dominio trabaja con
                # 0,13, igual que en todo el resto del sistema.
                tax_rate=(
                    None if fila.tax_rate is None else TaxRate(fila.tax_rate / 100)
                ),
                memo=fila.memo,
            )
            for fila in filas
        ]
