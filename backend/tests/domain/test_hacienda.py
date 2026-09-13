"""Lo que el dominio sabe de Hacienda (T-613, T-602b, T-617)."""

import pytest

from app.domain.errors import (
    InvalidEnvironment,
    InvalidIdentificationType,
    InvalidSigningKey,
)
from app.domain.hacienda import (
    DIMEX,
    ENVIRONMENTS,
    LEGAL,
    PHYSICAL,
    PRODUCTION,
    SANDBOX,
    check_environment,
    check_identification_type,
    endpoints,
    identification_type_for,
    signing_key_name,
)


class TestElAmbiente:
    def test_son_dos_y_en_ingles(self):
        # El POS ya publica 'sandbox' hoy. Tener dos vocablos para el mismo
        # estado es cómo se pierde una migración.
        assert ENVIRONMENTS == ("sandbox", "production")

    @pytest.mark.parametrize("bueno", ENVIRONMENTS)
    def test_los_dos_pasan(self, bueno):
        assert check_environment(bueno) == bueno

    @pytest.mark.parametrize("malo", ["produccion", "PRODUCTION", "prod", "", None, 1])
    def test_cualquier_otro_se_rechaza(self, malo):
        with pytest.raises(InvalidEnvironment):
            check_environment(malo)


class TestDondeViveHacienda:
    def test_sandbox_y_produccion_no_son_el_mismo_sitio(self):
        assert endpoints(SANDBOX) != endpoints(PRODUCTION)

    def test_el_sandbox_es_otra_RUTA_y_no_otro_servidor(self):
        # Es lo que se escribe mal de memoria: los dos salen del mismo dominio.
        pruebas, produccion = endpoints(SANDBOX), endpoints(PRODUCTION)
        assert "recepcion-sandbox" in pruebas.api_url
        assert "recepcion/v1" in produccion.api_url
        assert pruebas.api_url.split("/recepcion")[0] == produccion.api_url.split("/recepcion")[0]

    def test_el_realm_y_el_client_id_de_cada_uno(self):
        assert (endpoints(SANDBOX).realm, endpoints(SANDBOX).client_id) == (
            "rut-stag",
            "api-stag",
        )
        assert (endpoints(PRODUCTION).realm, endpoints(PRODUCTION).client_id) == (
            "rut",
            "api-prod",
        )

    def test_el_realm_esta_dentro_de_la_url_del_IdP(self):
        # Van separados igual: el realm se manda también en el cuerpo de algunas
        # peticiones, y sacarlo de la URL con un `split` sería fabricar un
        # acoplamiento entre dos datos que Hacienda publica por separado.
        for ambiente in ENVIRONMENTS:
            cual = endpoints(ambiente)
            assert f"/realms/{cual.realm}/" in cual.idp_url

    def test_un_ambiente_que_no_existe(self):
        with pytest.raises(InvalidEnvironment):
            endpoints("pruebas")


class TestLoQueElDespliegueSobreescribe:
    """La mitigación del riesgo TRIBU-CR: apuntar a otro lado el mismo día."""

    def test_sin_nada_que_cambiar(self):
        assert endpoints(PRODUCTION, None) == endpoints(PRODUCTION)
        assert endpoints(PRODUCTION, {}) == endpoints(PRODUCTION)

    def test_se_cambia_lo_que_se_pide_y_nada_mas(self):
        cambiado = endpoints(PRODUCTION, {"api_url": "https://tribu.example/v1/"})
        assert cambiado.api_url == "https://tribu.example/v1/"
        assert cambiado.realm == endpoints(PRODUCTION).realm

    def test_se_pueden_cambiar_los_cuatro(self):
        cambiado = endpoints(
            SANDBOX,
            {
                "api_url": "https://a/",
                "idp_url": "https://b/",
                "client_id": "c",
                "realm": "d",
            },
        )
        assert (cambiado.api_url, cambiado.idp_url, cambiado.client_id, cambiado.realm) == (
            "https://a/",
            "https://b/",
            "c",
            "d",
        )

    @pytest.mark.parametrize("vacio", ["", "   ", None])
    def test_una_variable_declarada_y_sin_valor_no_pisa_nada(self, vacio):
        # Es lo normal en un `.env` copiado del ejemplo. Dejarla pisar el valor
        # bueno convertiría el arranque en «no encuentra a Hacienda» sin
        # ninguna pista de por qué.
        assert endpoints(PRODUCTION, {"api_url": vacio}) == endpoints(PRODUCTION)

    def test_una_clave_que_no_es_de_las_cuatro_se_ignora(self):
        # Y no revienta: `replace` con un campo que no existe lanzaría
        # TypeError, y la causa sería una variable de entorno mal escrita.
        assert endpoints(PRODUCTION, {"timeout": "30"}) == endpoints(PRODUCTION)

    def test_se_recortan_los_bordes(self):
        # Un `.env` con un espacio al final es invisible y produce una URL que
        # no resuelve.
        cambiado = endpoints(PRODUCTION, {"realm": "  otro  "})
        assert cambiado.realm == "otro"


class TestElNombreDeLaLlaveDeFirma:
    def test_lleva_la_compania_y_el_ambiente(self):
        assert signing_key_name(7, PRODUCTION) == "fe-7-production"

    def test_dos_companias_no_comparten_llave(self):
        assert signing_key_name(7, PRODUCTION) != signing_key_name(8, PRODUCTION)

    def test_pruebas_y_produccion_tampoco(self):
        # Si compartieran, un ensayo se firmaría con el certificado de verdad.
        assert signing_key_name(7, SANDBOX) != signing_key_name(7, PRODUCTION)

    @pytest.mark.parametrize("malo", [0, -1, None, "7", 1.0, True])
    def test_no_se_compone_un_nombre_cualquiera(self, malo):
        # Un nombre cualquiera es la llave de otro. `True` entra en la lista a
        # propósito: en Python es un int y valdría 1.
        with pytest.raises(InvalidSigningKey):
            signing_key_name(malo, PRODUCTION)

    def test_ni_con_un_ambiente_inventado(self):
        with pytest.raises(InvalidEnvironment):
            signing_key_name(7, "pruebas")


class TestElTipoDeIdentificacion:
    @pytest.mark.parametrize("bueno", ["01", "02", "03", "04"])
    def test_los_cuatro_de_Hacienda(self, bueno):
        assert check_identification_type(bueno) == bueno

    @pytest.mark.parametrize("malo", ["05", "1", 1, "", None, "fisica"])
    def test_uno_inventado_no_lo_rechaza_el_sistema_sino_Hacienda(self, malo):
        with pytest.raises(InvalidIdentificationType):
            check_identification_type(malo)

    @pytest.mark.parametrize(
        "cedula, esperado",
        [
            ("112340567", PHYSICAL),
            ("3101234567", LEGAL),
            ("12345678901", DIMEX),
            ("123456789012", DIMEX),
        ],
    )
    def test_se_deduce_de_la_longitud(self, cedula, esperado):
        assert identification_type_for(cedula) == esperado

    def test_se_ignoran_los_separadores(self):
        # Hay cédulas guardadas como «1-0234-0567».
        assert identification_type_for("1-1234-0567") == PHYSICAL

    def test_una_juridica_y_un_NITE_no_se_distinguen(self):
        # Los dos son diez dígitos. Se elige jurídica porque es órdenes de
        # magnitud más común; devolver None dejaría a todos los clientes de
        # empresa sin tipo el día de facturar.
        assert identification_type_for("3101234567") == LEGAL

    @pytest.mark.parametrize("raro", ["", "12345", "1" * 13, None, 123456789])
    def test_lo_que_no_se_sabe_se_dice_que_no_se_sabe(self, raro):
        # `None` es «preguntá», y es distinto de un tipo equivocado.
        assert identification_type_for(raro) is None
