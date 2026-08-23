"""El idioma de la sesión (T-809, RN-28)."""

from app.domain.locale import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    effective_locale,
    normalize_locale,
)


class TestNormalizar:
    def test_los_tres_idiomas_pasan(self):
        assert [normalize_locale(x) for x in SUPPORTED_LOCALES] == list(SUPPORTED_LOCALES)

    def test_no_importan_espacios_ni_mayusculas(self):
        assert normalize_locale("  EN ") == "en"
        assert normalize_locale("Pt") == "pt"

    def test_una_region_cae_a_su_idioma(self):
        # La columna es de diez caracteres y alguien puede escribir `es-CR` a
        # mano; el POS tiene un catálogo por idioma, no por región.
        assert normalize_locale("es-CR") == "es"
        assert normalize_locale("pt_BR") == "pt"

    def test_un_idioma_sin_catalogo_se_descarta(self):
        # `fr` no está compilado: propagarlo dejaría la pantalla en español sin
        # que nadie lo haya pedido y sin aviso.
        assert normalize_locale("fr") is None
        assert normalize_locale("fr-CA") is None

    def test_lo_que_no_es_texto_se_descarta(self):
        for basura in (None, "", "   ", 7, [], {}):
            assert normalize_locale(basura) is None

    def test_un_sufijo_vacio_no_estorba(self):
        assert normalize_locale("es-") == "es"


class TestIdiomaEfectivo:
    def test_manda_lo_que_eligio_la_persona(self):
        assert effective_locale("en", "pt") == "en"

    def test_sin_eleccion_propia_hereda_la_compania(self):
        assert effective_locale(None, "pt") == "pt"

    def test_sin_ninguno_de_los_dos_es_espanol(self):
        assert effective_locale(None, None) == DEFAULT_LOCALE

    def test_una_eleccion_invalida_no_gana(self):
        # Lo que no se puede usar no puede tapar lo que sí: si la persona tiene
        # guardado un idioma que el POS no compiló, entra el de la compañía.
        assert effective_locale("fr", "pt") == "pt"
        assert effective_locale("fr", "de") == DEFAULT_LOCALE

    def test_el_vacio_no_es_una_eleccion(self):
        assert effective_locale("", "en") == "en"
