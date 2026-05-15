import pytest

from app.models import (
    Monetizacion,
    TipoDatoPersonal,
    TipoIA,
    TipoProyecto,
    QuestionnaireInput,
)
from app.rag import _build_user_message


def _make_input(**overrides):
    base = dict(
        tipo_proyecto=TipoProyecto.APP_WEB,
        descripcion_breve="Test project",
        tiene_usuarios_registrados=True,
        acceso_publico=False,
        tipos_datos_personales=[TipoDatoPersonal.EMAIL],
        usuarios_menores=False,
        usuarios_ue=True,
        transferencia_datos_terceros=False,
        usa_ia=True,
        tipo_ia=TipoIA.GENERATIVA,
        usa_cookies=False,
        monetizacion=Monetizacion.NINGUNA,
        contenido_digital=False,
        ccaa="Madrid",
        es_empresa=False,
        colegiado=None,
    )
    base.update(overrides)
    return QuestionnaireInput(**base)


@pytest.mark.parametrize(
    "tipo_proyecto,expected_value",
    [
        (TipoProyecto.APP_WEB, "app_web"),
        (TipoProyecto.API, "api"),
        (TipoProyecto.APP_MOVIL, "app_movil"),
        (TipoProyecto.SAAS, "saas"),
        (TipoProyecto.ECOMMERCE, "ecommerce"),
    ],
)
def test_tipo_proyecto_serializes_as_string_value(tipo_proyecto, expected_value):
    msg = _build_user_message(_make_input(tipo_proyecto=tipo_proyecto), [], [])
    assert expected_value in msg
    assert "TipoProyecto" not in msg


@pytest.mark.parametrize(
    "tipo_ia,expected_value",
    [
        (TipoIA.GENERATIVA, "generativa"),
        (TipoIA.AGENTES, "agentes"),
        (TipoIA.RECOMENDACION, "recomendacion"),
    ],
)
def test_tipo_ia_serializes_as_string_value(tipo_ia, expected_value):
    msg = _build_user_message(
        _make_input(usa_ia=True, tipo_ia=tipo_ia), [], []
    )
    assert expected_value in msg
    assert "TipoIA" not in msg


@pytest.mark.parametrize(
    "dato,expected_value",
    [
        (TipoDatoPersonal.EMAIL, "email"),
        (TipoDatoPersonal.SALUD, "salud"),
        (TipoDatoPersonal.BIOMETRICOS, "biometricos"),
    ],
)
def test_tipo_dato_personal_serializes_as_string_value(dato, expected_value):
    msg = _build_user_message(
        _make_input(tipos_datos_personales=[dato]), [], []
    )
    assert expected_value in msg
    assert "TipoDatoPersonal" not in msg
