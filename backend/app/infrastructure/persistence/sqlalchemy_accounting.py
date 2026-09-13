"""Los datos de contabilidad en SQLAlchemy (T-1107).

Adaptadores de `ports/accounting.py`. Ninguno confirma: escriben en la sesión que
les pasan y el `commit` lo da quien abrió la unidad de trabajo, igual que el
resto de los repositorios.

El `company_id` no se escribe en ninguna parte y no es un olvido: lo pone el
escuchador de `before_flush` (plan §3.3), el mismo que lo pone en una venta.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.model_accounting import Account, AccountingPeriod, AccountMapping
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
