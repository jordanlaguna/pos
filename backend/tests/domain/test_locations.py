"""La ubicación del emisor con los códigos de Hacienda (T-722, RN-83)."""

import pytest

from app.domain.errors import InvalidLocation
from app.domain.locations import (
    NEIGHBORHOOD_MAX,
    OTHER_SIGNS_MAX,
    check_location,
    is_blank,
    location_from_settings,
)
from app.domain.locations_data import CANTONS, DISTRICTS, PROVINCES

#: La del emisor de la factura de referencia: San José, San José, Zapote.
ZAPOTE = dict(
    province="1",
    canton="01",
    district="05",
    other_signs="600 mts. oeste de Plaza Cristal, frente al Archivo Nacional",
)


class TestElCatalogo:
    """Lo que dice la nota 14 (`Codificacionubicacion_V4.4`, noviembre de 2024)."""

    def test_siete_provincias(self):
        assert list(PROVINCES) == ["1", "2", "3", "4", "5", "6", "7"]

    def test_ochenta_y_cuatro_cantones(self):
        assert sum(len(c) for c in CANTONS.values()) == 84

    def test_cuatrocientos_noventa_y_dos_distritos(self):
        assert sum(len(d) for d in DISTRICTS.values()) == 492

    def test_los_cantones_nuevos_estan(self):
        # Río Cuarto (2017), Monteverde (2021) y Puerto Jiménez (2022): un
        # catálogo viejo no los tendría y esos negocios no podrían emitir.
        assert CANTONS["2"]["16"] == "Río Cuarto"
        assert CANTONS["6"]["12"] == "Monte Verde"
        assert CANTONS["6"]["13"] == "Puerto Jimenez"

    def test_los_codigos_llevan_sus_ceros(self):
        assert all(len(c) == 2 for cantones in CANTONS.values() for c in cantones)
        assert all(len(d) == 2 for distritos in DISTRICTS.values() for d in distritos)

    def test_cada_distrito_cuelga_de_un_canton_que_existe(self):
        for llave in DISTRICTS:
            provincia, canton = llave.split("-")
            assert canton in CANTONS[provincia], llave

    def test_los_nombres_no_quedan_en_mayusculas(self):
        # El Excel repite cada nombre en mayúsculas en la primera fila de su grupo.
        assert DISTRICTS["1-01"]["05"] == "Zapote"
        assert DISTRICTS["3-02"]["06"] == "Birrisito"


class TestUnaUbicacionQueSirve:
    def test_la_de_la_factura_de_referencia(self):
        ubicacion = check_location(**ZAPOTE)
        assert (ubicacion.province, ubicacion.canton, ubicacion.district) == ("1", "01", "05")
        assert ubicacion.neighborhood == ""
        assert ubicacion.names == ("San José", "San José", "Zapote")

    def test_los_ceros_se_ponen_solos(self):
        ubicacion = check_location(**{**ZAPOTE, "canton": "1", "district": 5, "province": 1})
        assert (ubicacion.province, ubicacion.canton, ubicacion.district) == ("1", "01", "05")

    def test_el_barrio_es_opcional_y_se_guarda_si_viene(self):
        assert check_location(**ZAPOTE, neighborhood="  Barrio   Los Ángeles ").neighborhood == (
            "Barrio Los Ángeles"
        )

    def test_los_espacios_de_mas_se_quitan(self):
        assert check_location(**{**ZAPOTE, "other_signs": "  frente   al  parque "}).other_signs == (
            "frente al parque"
        )


class TestUnCodigoSoloValeDentroDeSuPadre:
    def test_un_canton_de_otra_provincia(self):
        # Limón tiene seis cantones: el 07 no existe ahí.
        with pytest.raises(InvalidLocation) as e:
            check_location(**{**ZAPOTE, "province": "7", "canton": "07"})
        assert (e.value.field, e.value.reason) == ("canton", "unknown")

    def test_un_distrito_de_otro_canton(self):
        # Curridabat tiene cuatro distritos.
        with pytest.raises(InvalidLocation) as e:
            check_location(**{**ZAPOTE, "canton": "18", "district": "05"})
        assert (e.value.field, e.value.reason) == ("district", "unknown")

    @pytest.mark.parametrize("provincia", ["0", "8", "9", "12", "a", "１"])
    def test_una_provincia_que_no_existe(self, provincia):
        with pytest.raises(InvalidLocation) as e:
            check_location(**{**ZAPOTE, "province": provincia})
        assert (e.value.field, e.value.reason) == ("province", "unknown")


class TestLoQueFalta:
    @pytest.mark.parametrize("campo", ["province", "canton", "district", "other_signs"])
    @pytest.mark.parametrize("vacio", [None, "", "   "])
    def test_los_cuatro_obligatorios(self, campo, vacio):
        with pytest.raises(InvalidLocation) as e:
            check_location(**{**ZAPOTE, campo: vacio})
        assert (e.value.field, e.value.reason) == (campo, "required")

    def test_un_booleano_no_es_un_codigo(self):
        with pytest.raises(InvalidLocation) as e:
            check_location(**{**ZAPOTE, "province": True})
        assert e.value.reason == "required"


class TestLosLargosDelAnexo:
    def test_otras_senas_de_menos_de_cinco(self):
        with pytest.raises(InvalidLocation) as e:
            check_location(**{**ZAPOTE, "other_signs": "casa"})
        assert (e.value.field, e.value.reason) == ("other_signs", "too_short")

    def test_otras_senas_de_mas(self):
        with pytest.raises(InvalidLocation) as e:
            check_location(**{**ZAPOTE, "other_signs": "x" * (OTHER_SIGNS_MAX + 1)})
        assert (e.value.field, e.value.reason) == ("other_signs", "too_long")

    def test_el_barrio_tambien_tiene_minimo(self):
        with pytest.raises(InvalidLocation) as e:
            check_location(**ZAPOTE, neighborhood="Sur")
        assert (e.value.field, e.value.reason) == ("neighborhood", "too_short")

    def test_y_maximo(self):
        with pytest.raises(InvalidLocation) as e:
            check_location(**ZAPOTE, neighborhood="x" * (NEIGHBORHOOD_MAX + 1))
        assert (e.value.field, e.value.reason) == ("neighborhood", "too_long")

    def test_un_barrio_que_no_es_texto(self):
        with pytest.raises(InvalidLocation) as e:
            check_location(**ZAPOTE, neighborhood=12345)
        assert (e.value.field, e.value.reason) == ("neighborhood", "unknown")


class TestComoLaGuardaConfiguracion:
    """`business.location`, con las llaves del JSON del POS."""

    def test_se_lee_con_otherSigns(self):
        ubicacion = location_from_settings(
            {"province": "1", "canton": "01", "district": "05", "otherSigns": "frente al Archivo"}
        )
        assert ubicacion.other_signs == "frente al Archivo"

    def test_algo_que_no_es_un_objeto_es_una_que_falta(self):
        with pytest.raises(InvalidLocation) as e:
            location_from_settings("San José")
        assert (e.value.field, e.value.reason) == ("province", "required")

    @pytest.mark.parametrize(
        "vacia",
        [None, {}, {"province": "", "canton": None, "otherSigns": "  "}],
    )
    def test_vacia_del_todo(self, vacia):
        assert is_blank(vacia)

    @pytest.mark.parametrize(
        "a_medias",
        [{"province": "1"}, {"otherSigns": "frente al parque"}, "San José", {"district": 5}],
    )
    def test_a_medias_no_es_vacia(self, a_medias):
        # La vacía se guarda —quien no emite no tiene por qué dar su distrito—;
        # la a medias es un error de quien escribe.
        assert not is_blank(a_medias)
