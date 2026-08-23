"""El estado de la suscripción (T-308, RF-10, RF-11, RN-1, RN-2).

Todas las pruebas fijan «hoy» a mano. Es lo que permite pararse en el día 7 de
la gracia y en el 8 sin esperar una semana, y la razón por la que `evaluar`
recibe la fecha en vez de leer el reloj.
"""

from datetime import date

from app.domain.subscription import (
    DIAS_DE_AVISO,
    DIAS_DE_GRACIA,
    ESTADOS,
    Suscripcion,
    dias_restantes,
    estado_efectivo,
    evaluar,
    motivo_de_bloqueo,
)

HOY = date(2026, 8, 23)


def dentro(dias: int) -> date:
    """La fecha que queda a `dias` de hoy. Negativo = ya pasó."""
    return date.fromordinal(HOY.toordinal() + dias)


class TestDiasRestantes:
    def test_una_fecha_futura_cuenta_hacia_adelante(self):
        assert dias_restantes(dentro(10), HOY) == 10

    def test_vencer_hoy_es_cero(self):
        assert dias_restantes(HOY, HOY) == 0

    def test_una_fecha_pasada_es_negativa(self):
        assert dias_restantes(dentro(-3), HOY) == -3

    def test_sin_fecha_no_hay_cuenta(self):
        # Distinto de 0: 0 es «vence hoy» y esto es «nadie escribió la fecha».
        assert dias_restantes(None, HOY) is None


class TestEstadoEfectivo:
    def test_activa_con_fecha_pasada_esta_vencida(self):
        # El vencimiento lo pone el calendario, no una tarea manual: si esperara
        # a que soporte cambie la columna, el sistema dejaría de cobrar el día
        # que nadie mire.
        assert estado_efectivo("activa", dentro(-1), HOY) == "vencida"

    def test_prueba_con_fecha_pasada_tambien(self):
        assert estado_efectivo("prueba", dentro(-1), HOY) == "vencida"

    def test_el_dia_del_vencimiento_todavia_no_vencio(self):
        assert estado_efectivo("activa", HOY, HOY) == "activa"

    def test_sin_fecha_el_estado_no_se_mueve(self):
        assert estado_efectivo("activa", None, HOY) == "activa"

    def test_suspendida_y_cancelada_no_las_mueve_el_calendario(self):
        # Son decisiones de soporte. Que la fecha haya pasado no las convierte
        # en algo más leve.
        assert estado_efectivo("suspendida", dentro(-100), HOY) == "suspendida"
        assert estado_efectivo("cancelada", dentro(-100), HOY) == "cancelada"

    def test_vencida_se_queda_vencida_aunque_la_fecha_no_haya_llegado(self):
        assert estado_efectivo("vencida", dentro(30), HOY) == "vencida"


class TestQuienEntra:
    def test_prueba_y_activa_entran(self):
        for estado in ("prueba", "activa"):
            assert evaluar(estado, dentro(30), HOY).puede_entrar

    def test_vencida_entra(self):
        # Dejar de pagar es dejar de vender, no dejar de entrar: los datos
        # siguen siendo del cliente y tiene que poder consultarlos.
        assert evaluar("vencida", dentro(-30), HOY).puede_entrar

    def test_suspendida_solo_el_administrador(self):
        assert evaluar("suspendida", HOY, HOY, rol="admin").puede_entrar
        assert not evaluar("suspendida", HOY, HOY, rol="cajero").puede_entrar

    def test_cancelada_no_entra_nadie(self):
        assert not evaluar("cancelada", HOY, HOY, rol="admin").puede_entrar

    def test_un_estado_inventado_no_entra(self):
        # Falla cerrado: un error de dedo en la base cierra la puerta en vez de
        # abrirla.
        assert not evaluar("activaa", HOY, HOY).puede_entrar

    def test_el_rol_por_omision_es_administrador(self):
        # El panel de soporte pregunta sin tener a nadie en frente.
        assert evaluar("suspendida", HOY, HOY).puede_entrar


class TestQuienVende:
    def test_activa_vende(self):
        assert evaluar("activa", dentro(30), HOY).puede_vender

    def test_en_prueba_se_vende(self):
        assert evaluar("prueba", dentro(3), HOY).puede_vender

    def test_el_primer_dia_de_gracia_se_vende(self):
        estado = evaluar("activa", dentro(-1), HOY)
        assert estado.estado == "vencida"
        assert estado.puede_vender
        assert estado.gracia == DIAS_DE_GRACIA

    def test_el_ultimo_dia_de_gracia_se_vende(self):
        estado = evaluar("activa", dentro(-DIAS_DE_GRACIA), HOY)
        assert estado.puede_vender
        assert estado.gracia == 1

    def test_pasada_la_gracia_no_se_vende(self):
        estado = evaluar("activa", dentro(-DIAS_DE_GRACIA - 1), HOY)
        assert not estado.puede_vender
        assert estado.gracia == 0

    def test_suspendida_no_vende_ni_para_el_administrador(self):
        # Entra, pero solo a ver el aviso de pago.
        estado = evaluar("suspendida", dentro(30), HOY, rol="admin")
        assert estado.puede_entrar
        assert not estado.puede_vender

    def test_cancelada_no_vende(self):
        assert not evaluar("cancelada", dentro(30), HOY).puede_vender

    def test_vencida_sin_fecha_queda_en_solo_lectura(self):
        # Sin fecha no hay gracia que calcular. Falla cerrado: solo lectura es
        # lo peor que le puede pasar a quien olvidó un dato; vender gratis para
        # siempre es lo peor que le puede pasar al negocio.
        estado = evaluar("vencida", None, HOY)
        assert estado.puede_entrar
        assert not estado.puede_vender
        assert estado.gracia == 0

    def test_marcar_vencida_antes_de_la_fecha_no_regala_gracia_extra(self):
        # La cuenta empieza cuando la fecha pasa: con el vencimiento a 30 días,
        # la gracia se topa en los siete de siempre y no en 37.
        assert evaluar("vencida", dentro(30), HOY).gracia == DIAS_DE_GRACIA


class TestElAviso:
    def test_una_prueba_avisa_siempre_cuando_vence(self):
        assert evaluar("prueba", dentro(30), HOY).aviso == "en_prueba"

    def test_una_prueba_por_vencer_avisa_con_urgencia(self):
        assert evaluar("prueba", dentro(2), HOY).aviso == "vence_pronto"

    def test_activa_no_avisa_nada_de_lejos(self):
        assert evaluar("activa", dentro(DIAS_DE_AVISO + 1), HOY).aviso is None

    def test_activa_avisa_una_semana_antes(self):
        assert evaluar("activa", dentro(DIAS_DE_AVISO), HOY).aviso == "vence_pronto"

    def test_el_dia_del_vencimiento_avisa(self):
        assert evaluar("activa", HOY, HOY).aviso == "vence_pronto"

    def test_activa_sin_fecha_no_avisa(self):
        assert evaluar("activa", None, HOY).aviso is None

    def test_dentro_de_la_gracia_el_aviso_lo_dice(self):
        assert evaluar("activa", dentro(-2), HOY).aviso == "en_gracia"

    def test_pasada_la_gracia_el_aviso_cambia(self):
        assert evaluar("activa", dentro(-30), HOY).aviso == "solo_lectura"

    def test_suspendida_y_cancelada_tienen_su_propio_aviso(self):
        assert evaluar("suspendida", HOY, HOY).aviso == "suspendida"
        assert evaluar("cancelada", HOY, HOY).aviso == "cancelada"

    def test_un_estado_inventado_no_avisa_nada(self):
        assert evaluar("qué", None, HOY).aviso is None


class TestLoQueSeDevuelve:
    def test_el_estado_guardado_viaja_junto_al_efectivo(self):
        # El panel de soporte muestra lo que alguien puso, no lo que el sistema
        # dedujo: si dice «activa» y el sistema la trata como vencida, hay que
        # poder ver las dos cosas.
        estado = evaluar("activa", dentro(-1), HOY)
        assert (estado.guardado, estado.estado) == ("activa", "vencida")

    def test_es_inmutable(self):
        # Un `dataclass(frozen=True)`: nadie le cambia el estado a la respuesta
        # a mitad de camino.
        estado = evaluar("activa", HOY, HOY)
        assert isinstance(estado, Suscripcion)
        try:
            estado.puede_vender = True  # type: ignore[misc]
        except Exception as exc:
            assert "assign" in str(exc) or "immutable" in str(exc).lower()
        else:
            raise AssertionError("Suscripcion tendría que ser inmutable")

    def test_la_fecha_vuelve_tal_cual(self):
        assert evaluar("activa", dentro(5), HOY).vence_el == dentro(5)


class TestElMotivo:
    def test_quien_entra_no_tiene_motivo(self):
        assert motivo_de_bloqueo(evaluar("activa", HOY, HOY)) is None

    def test_el_motivo_es_el_estado_efectivo(self):
        assert motivo_de_bloqueo(evaluar("cancelada", HOY, HOY)) == "cancelada"
        assert motivo_de_bloqueo(evaluar("suspendida", HOY, HOY, rol="cajero")) == "suspendida"


class TestLaLista:
    def test_los_cinco_estados_del_spec(self):
        assert ESTADOS == ("prueba", "activa", "vencida", "suspendida", "cancelada")

    def test_los_cinco_se_pueden_evaluar_sin_reventar(self):
        # Que ninguno quede sin caso: el día que se agregue un estado, esta
        # prueba obliga a decidir qué hace.
        for estado in ESTADOS:
            resultado = evaluar(estado, HOY, HOY)
            assert isinstance(resultado.puede_entrar, bool)
            assert isinstance(resultado.puede_vender, bool)
