"""Las credenciales de Hacienda en SQLAlchemy (T-603, adaptador de `ports/fe_credentials.py`).

No confirma: escribe en la sesión que le pasan y el `commit` lo da quien abrió
la unidad de trabajo, igual que el resto de los repositorios.

El `company_id` no se escribe en ninguna parte y no es un olvido: lo pone el
escuchador de `before_flush` (plan §3.3), el mismo que lo pone en una venta. Y
como acá entra en una **llave primaria compuesta**, eso significa además que la
fila no tiene identidad completa hasta el `flush` — de ahí el `flush()` explícito
después de cada alta.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.model_fe import FeCredentials

#: Lo que dice `key_custody` cuando hay certificado. Una sola custodia desde el
#: 2026-09-13: la llave privada vive en Vault y no hay otro camino.
VAULT = "vault"


class SqlAlchemyFeCredentialsRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, environment: str) -> FeCredentials | None:
        return (
            self._db.query(FeCredentials)
            .filter(FeCredentials.environment == environment)
            .first()
        )

    def all(self) -> list[FeCredentials]:
        return self._db.query(FeCredentials).order_by(FeCredentials.environment).all()

    def _fila(self, environment: str) -> FeCredentials:
        """La fila del ambiente, creándola vacía si no estaba.

        Un ambiente sin fila y uno con la fila vacía son **el mismo estado** —no
        configurado—, así que crearla acá no cambia lo que ve nadie. Lo que
        evita es que cada método tenga que decidir si inserta o actualiza.
        """
        fila = self.get(environment)
        if fila is None:
            fila = FeCredentials(environment=environment)
            self._db.add(fila)
            self._db.flush()
        return fila

    # ------------------------------------------------------------------ firma

    def save_certificate(
        self,
        *,
        environment: str,
        certificate_pem: str,
        certificate_name: str,
        expires_at: datetime,
        uploaded_at: datetime,
        uploaded_by: int,
    ) -> None:
        fila = self._fila(environment)
        fila.certificate_pem = certificate_pem
        fila.certificate_name = certificate_name
        fila.expires_at = expires_at
        fila.cert_uploaded_at = uploaded_at
        fila.cert_uploaded_by = uploaded_by
        fila.key_custody = VAULT

    def clear_certificate(self, *, environment: str) -> None:
        fila = self.get(environment)
        if fila is None:
            return
        fila.certificate_pem = None
        fila.certificate_name = None
        fila.expires_at = None
        fila.cert_uploaded_at = None
        fila.cert_uploaded_by = None
        fila.key_custody = None

    # ------------------------------------------------------------ transmisión

    def save_atv(
        self,
        *,
        environment: str,
        user: str,
        password_encrypted: str,
        updated_at: datetime,
        updated_by: int,
    ) -> None:
        fila = self._fila(environment)
        fila.atv_user = user
        fila.atv_password_encrypted = password_encrypted
        fila.atv_updated_at = updated_at
        fila.atv_updated_by = updated_by
        # La verificación anterior deja de valer: son otras credenciales. Sin
        # esto, la pantalla seguiría diciendo «verificadas el 3 de septiembre»
        # sobre una contraseña que se cambió hoy y que nadie probó.
        fila.atv_verified_at = None

    def mark_verified(self, *, environment: str, at: datetime) -> None:
        fila = self.get(environment)
        if fila is None:
            return
        fila.atv_verified_at = at
