import pytest

from app.domain.barcode import MAX_LENGTH, Barcode
from app.domain.errors import InvalidBarcode


class TestValidos:
    @pytest.mark.parametrize(
        "codigo", ["7441029001057", "ABC-123", "T1755331234", "1", "x" * MAX_LENGTH]
    )
    def test_lo_que_produce_un_lector(self, codigo):
        assert Barcode(codigo).value == codigo

    def test_recorta_los_bordes(self):
        # El lector manda un Enter y a veces espacios de relleno.
        assert Barcode("  7441029001057  ") == Barcode("7441029001057")

    def test_se_imprime_como_su_texto(self):
        assert str(Barcode("7441029001057")) == "7441029001057"

    def test_dos_iguales_son_el_mismo(self):
        assert len({Barcode("A1"), Barcode(" A1 ")}) == 1

    def test_se_ordenan(self):
        assert sorted([Barcode("B"), Barcode("A")]) == [Barcode("A"), Barcode("B")]


class TestInvalidos:
    @pytest.mark.parametrize("malo", ["", "   ", "\t\n"])
    def test_vacio(self, malo):
        with pytest.raises(InvalidBarcode) as e:
            Barcode(malo)
        assert e.value.motivo == "vacío"

    def test_con_espacios_en_medio(self):
        # Dos lecturas pegadas. Buscar por eso no encuentra nada.
        with pytest.raises(InvalidBarcode) as e:
            Barcode("744102 9001057")
        assert "espacios" in e.value.motivo

    def test_mas_largo_que_la_columna(self):
        # Cortar en silencio convertiría dos productos distintos en el mismo.
        with pytest.raises(InvalidBarcode) as e:
            Barcode("x" * (MAX_LENGTH + 1))
        assert str(MAX_LENGTH) in e.value.motivo

    def test_con_caracteres_de_control(self):
        with pytest.raises(InvalidBarcode) as e:
            Barcode("744\x00102")
        assert "control" in e.value.motivo

    @pytest.mark.parametrize("malo", [None, 7441029001057, [], object()])
    def test_lo_que_no_es_texto(self, malo):
        with pytest.raises(InvalidBarcode) as e:
            Barcode(malo)
        assert e.value.motivo == "no es texto"

    def test_el_error_lleva_el_valor_original(self):
        with pytest.raises(InvalidBarcode) as e:
            Barcode("  ")
        assert e.value.value == "  "
