"""El estado de las credenciales de un ambiente (T-604, T-606, T-610)."""

from datetime import datetime, timedelta

import pytest

from app.domain.errors import InvalidEnvironment
from app.domain.fe_credentials import (
    EXPIRED,
    EXPIRING,
    MISSING,
    VALID,
    WARNING_DAYS,
    certificate_status,
    days_left,
    environment_status,
)
from app.domain.hacienda import PRODUCTION, SANDBOX

AHORA = datetime(2026, 9, 13, 11, 0, 0)


def dentro_de(**cuanto) -> datetime:
    return AHORA + timedelta(**cuanto)


class TestElAviso:
    def test_en_el_dia_31_no_avisa_y_en_el_30_si(self):
        # Es la verificación literal de T-606.
        assert certificate_status(dentro_de(days=WARNING_DAYS + 1), AHORA) == VALID
        assert certificate_status(dentro_de(days=WARNING_DAYS), AHORA) == EXPIRING

    def test_sin_certificado_no_hay_nada_que_avisar(self):
        assert certificate_status(None, AHORA) == MISSING
        assert days_left(None, AHORA) is None

    def test_vencido_es_su_propio_estado_y_no_un_aviso_mas_fuerte(self):
        # La diferencia importa: con uno por vencer se puede emitir, con uno
        # vencido no. Un solo estado «avisar» las juntaría.
        assert certificate_status(dentro_de(seconds=-1), AHORA) == EXPIRED

    def test_el_instante_exacto_del_vencimiento_ya_es_vencido(self):
        assert certificate_status(AHORA, AHORA) == EXPIRED

    def test_la_hora_cuenta_y_no_solo_el_dia(self):
        # La columna es DATETIME a propósito: uno que vence a las 10:00 no sirve
        # a las 11:00. Redondeando a días, el sistema diría que sirve durante
        # catorce horas en las que no sirve — un día de facturación entero.
        vence_hoy_temprano = datetime(2026, 9, 13, 10, 0, 0)
        assert certificate_status(vence_hoy_temprano, AHORA) == EXPIRED

    def test_lo_que_queda_se_trunca_hacia_abajo(self):
        # Veintitrés horas son 0 días y no 1: lo que queda no alcanza para un
        # día más de trabajo.
        assert days_left(dentro_de(hours=23), AHORA) == 0
        assert days_left(dentro_de(hours=25), AHORA) == 1

    def test_lo_vencido_cuenta_en_negativo(self):
        assert days_left(dentro_de(days=-3), AHORA) == -3


class TestElEstadoDeUnAmbiente:
    def test_un_ambiente_que_nunca_se_configuro_tambien_tiene_estado(self):
        # Devolver None obligaría a quien llama a inventar el caso vacío, que es
        # donde se pierde la mitad de RF-30: la pantalla tiene que poder decir
        # qué le falta a cada ambiente.
        estado = environment_status(environment=SANDBOX, now=AHORA)
        assert estado.certificate_configured is False
        assert estado.atv_configured is False
        assert estado.ready is False

    def test_listo_es_certificado_Y_credenciales(self):
        solo_certificado = environment_status(
            environment=PRODUCTION, now=AHORA, expires_at=dentro_de(days=200)
        )
        assert solo_certificado.ready is False

        solo_atv = environment_status(
            environment=PRODUCTION, now=AHORA, atv_configured=True
        )
        assert solo_atv.ready is False

        completo = environment_status(
            environment=PRODUCTION,
            now=AHORA,
            expires_at=dentro_de(days=200),
            atv_configured=True,
        )
        assert completo.ready is True

    def test_un_certificado_vencido_esta_configurado_y_NO_esta_listo(self):
        # Es la condición que se olvida. Una pantalla que mostrara
        # «certificado ✓ · ATV ✓» sin mirar la fecha diría que todo está listo
        # justo el día que dejó de estarlo.
        estado = environment_status(
            environment=PRODUCTION,
            now=AHORA,
            expires_at=dentro_de(days=-1),
            atv_configured=True,
        )
        assert estado.certificate_configured is True
        assert estado.ready is False

    def test_uno_por_vencer_todavia_emite(self):
        # Avisar no es impedir: con veintinueve días por delante se factura
        # igual, y el aviso está para que nadie llegue al día cero.
        estado = environment_status(
            environment=PRODUCTION,
            now=AHORA,
            expires_at=dentro_de(days=29),
            atv_configured=True,
        )
        assert estado.certificate_status == EXPIRING
        assert estado.ready is True

    def test_no_lleva_el_archivo_ni_el_PIN_ni_la_contrasena(self):
        # No existe el camino (RF-23, RN-16). El PIN además ya no se guarda en
        # ninguna parte desde que la llave vive en Vault.
        estado = environment_status(
            environment=PRODUCTION, now=AHORA, atv_user="cpf-01-1234-5678"
        )
        campos = set(vars(estado))
        assert not (campos & {"p12", "pin", "password", "atv_password"})
        # El usuario sí: es un identificador y sin verlo nadie puede comprobar
        # que escribió el que era.
        assert estado.atv_user == "cpf-01-1234-5678"

    def test_un_ambiente_inventado_no_tiene_estado(self):
        with pytest.raises(InvalidEnvironment):
            environment_status(environment="pruebas", now=AHORA)

    @pytest.mark.parametrize("ambiente", [SANDBOX, PRODUCTION])
    def test_los_dos_ambientes_se_preguntan_igual(self, ambiente):
        assert environment_status(environment=ambiente, now=AHORA).environment == ambiente
