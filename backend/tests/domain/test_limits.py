"""Los límites del plan (T-309, RF-12)."""

from app.domain.limits import RECURSOS, SIN_LIMITE, cupo, hay_lugar, sin_limite


class TestSinLimite:
    def test_el_negativo_es_la_marca(self):
        assert sin_limite(SIN_LIMITE)
        assert sin_limite(-99)

    def test_cero_no_es_sin_limite(self):
        # Es la decisión del módulo: 0 es lo que queda cuando alguien inserta un
        # plan a medio llenar, así que bloquea. «Sin techo» se escribe −1.
        assert not sin_limite(0)

    def test_un_maximo_normal_no_es_sin_limite(self):
        assert not sin_limite(3)


class TestHayLugar:
    def test_cabe_mientras_falte(self):
        assert hay_lugar(2, 3)

    def test_no_cabe_al_llegar_al_maximo(self):
        # Con el máximo en 3 y tres existentes, el cuarto no cabe: el que se
        # está creando todavía no está contado.
        assert not hay_lugar(3, 3)

    def test_no_cabe_si_ya_hay_de_mas(self):
        # Puede pasar al recortarle el plan a un cliente que ya creció.
        assert not hay_lugar(5, 3)

    def test_con_maximo_en_cero_no_cabe_ninguno(self):
        assert not hay_lugar(0, 0)

    def test_sin_limite_siempre_cabe(self):
        assert hay_lugar(0, SIN_LIMITE)
        assert hay_lugar(9999, SIN_LIMITE)


class TestCupo:
    def test_cuenta_lo_que_falta(self):
        assert cupo(2, 5) == 3

    def test_lleno_es_cero(self):
        assert cupo(5, 5) == 0

    def test_pasado_el_maximo_tampoco_es_negativo(self):
        # Lo que significa es «ninguno más», y los que ya existen no se borran
        # por haberle recortado el plan.
        assert cupo(8, 5) == 0

    def test_sin_limite_no_tiene_cupo_que_contar(self):
        assert cupo(3, SIN_LIMITE) is None


class TestLosRecursos:
    def test_son_los_tres_del_plan_y_en_ingles(self):
        # Viajan al POS en los datos del error, así que son parte del contrato
        # del API y van en inglés como el resto.
        assert RECURSOS == ("branches", "terminals", "users")
