import pytest
from pydantic import ValidationError

from app.models import QuestionnaireInput, RAGResponse


def test_questionnaire_input_valid(sample_input_dict):
    q = QuestionnaireInput(**sample_input_dict)
    assert q.tipo_proyecto == "app_web"
    assert q.tiene_usuarios_registrados is True
    assert q.tipos_datos_personales == ["nombre", "email"]
    assert q.tipo_ia == "generativa"
    assert q.colegiado is None


def test_questionnaire_input_minimal():
    q = QuestionnaireInput(
        tipo_proyecto="api",
        descripcion_breve="API pública de consulta meteorológica",
        tiene_usuarios_registrados=False,
        acceso_publico=True,
        tipos_datos_personales=["ninguno"],
        usuarios_menores=False,
        usuarios_ue=False,
        transferencia_datos_terceros=False,
        usa_ia=False,
        usa_cookies=False,
        contenido_digital=False,
        ccaa="Madrid",
        es_empresa=True,
    )
    assert q.tipo_ia is None
    assert q.monetizacion is None
    assert q.colegiado is None


def test_questionnaire_input_descripcion_max_length():
    with pytest.raises(ValidationError):
        QuestionnaireInput(
            tipo_proyecto="app_web",
            descripcion_breve="x" * 501,
            tiene_usuarios_registrados=False,
            acceso_publico=True,
            tipos_datos_personales=["ninguno"],
            usuarios_menores=False,
            usuarios_ue=False,
            transferencia_datos_terceros=False,
            usa_ia=False,
            usa_cookies=False,
            contenido_digital=False,
            ccaa="Madrid",
            es_empresa=True,
        )


def test_questionnaire_input_usa_ia_without_tipo_ia_raises():
    with pytest.raises(ValidationError, match="tipo_ia es obligatorio"):
        QuestionnaireInput(
            tipo_proyecto="app_web",
            descripcion_breve="App con IA",
            tiene_usuarios_registrados=True,
            acceso_publico=False,
            tipos_datos_personales=["email"],
            usuarios_menores=False,
            usuarios_ue=True,
            transferencia_datos_terceros=False,
            usa_ia=True,
            tipo_ia=None,
            usa_cookies=False,
            contenido_digital=False,
            ccaa="Madrid",
            es_empresa=False,
        )


def test_rag_response():
    r = RAGResponse(
        respuesta_completa="Debes implementar consentimiento explícito según el RGPD.",
        normativas_detectadas=["RGPD", "LOPDGDD"],
        chunks_utilizados=5,
        disclaimer="⚠️ Esta información es orientativa.",
    )
    assert r.chunks_utilizados == 5
    assert "RGPD" in r.normativas_detectadas
