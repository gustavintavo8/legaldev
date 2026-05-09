import pytest
from unittest.mock import MagicMock
from app.rag import run_pipeline, DISCLAIMER
from app.config import settings
from app.rag import _build_query
from app.models import QuestionnaireInput


def _make_input(**overrides):
    base = dict(
        tipo_proyecto="app_web",
        descripcion_breve="App de gestión",
        tiene_usuarios_registrados=True,
        acceso_publico=False,
        tipos_datos_personales=["email"],
        usuarios_menores=False,
        usuarios_ue=True,
        transferencia_datos_terceros=False,
        usa_ia=False,
        tipo_ia=None,
        usa_cookies=False,
        monetizacion=None,
        contenido_digital=False,
        ccaa="Madrid",
        es_empresa=False,
        colegiado=None,
    )
    base.update(overrides)
    return QuestionnaireInput(**base)


def test_build_query_includes_tipo_proyecto():
    assert "api" in _build_query(_make_input(tipo_proyecto="api"))


def test_build_query_includes_datos_personales():
    result = _build_query(_make_input(tipos_datos_personales=["salud", "ubicacion"]))
    assert "datos personales" in result
    assert "salud" in result
    assert "ubicacion" in result


def test_build_query_excludes_ninguno():
    result = _build_query(_make_input(tipos_datos_personales=["ninguno"]))
    assert "datos personales" not in result


def test_build_query_ia_with_tipo():
    result = _build_query(_make_input(usa_ia=True, tipo_ia="generativa"))
    assert "inteligencia artificial" in result
    assert "generativa" in result


def test_build_query_ia_without_tipo():
    result = _build_query(_make_input(usa_ia=True, tipo_ia=None))
    assert "inteligencia artificial" in result


def test_build_query_no_ia():
    result = _build_query(_make_input(usa_ia=False))
    assert "inteligencia artificial" not in result


def test_build_query_cookies():
    assert "cookies" in _build_query(_make_input(usa_cookies=True))


def test_build_query_usuarios_menores():
    assert "menores" in _build_query(_make_input(usuarios_menores=True))


def test_build_query_always_includes_ccaa_and_spain():
    result = _build_query(_make_input(ccaa="Cataluña"))
    assert "Cataluña" in result
    assert "España" in result


def test_build_query_monetizacion_ninguna_excluded():
    assert "ninguna" not in _build_query(_make_input(monetizacion="ninguna"))


def test_build_query_monetizacion_included():
    assert "publicidad" in _build_query(_make_input(monetizacion="publicidad"))


@pytest.fixture
def sample_input():
    return _make_input()


def _make_mock_doc(source="RGPD.pdf", doc_type="normativa_europea"):
    doc = MagicMock()
    doc.page_content = f"Contenido de prueba de {source}"
    doc.metadata = {"source": source, "doc_type": doc_type}
    return doc


def _make_state(docs, llm_response="Respuesta de prueba"):
    state = MagicMock()
    state.vectorstore.similarity_search.return_value = docs
    state.groq_client.invoke.return_value = MagicMock(content=llm_response)
    return state


def test_run_pipeline_returns_rag_response(sample_input):
    docs = [
        _make_mock_doc("RGPD.pdf"),
        _make_mock_doc("LOPDGDD.pdf", "normativa_española"),
    ]
    state = _make_state(docs, "Debes implementar consentimiento explícito.")

    result = run_pipeline(sample_input, state)

    assert result.respuesta_completa == "Debes implementar consentimiento explícito."
    assert result.chunks_utilizados == 2
    assert result.disclaimer == DISCLAIMER
    assert "RGPD" in result.normativas_detectadas
    assert "LOPDGDD" in result.normativas_detectadas


def test_run_pipeline_normativas_deduplicadas(sample_input):
    docs = [_make_mock_doc("RGPD.pdf"), _make_mock_doc("RGPD.pdf")]
    result = run_pipeline(sample_input, _make_state(docs))
    assert result.normativas_detectadas.count("RGPD") == 1


def test_run_pipeline_groq_error_raises_503(sample_input):
    state = MagicMock()
    state.vectorstore.similarity_search.return_value = [_make_mock_doc()]
    state.groq_client.invoke.side_effect = Exception("Connection refused")

    with pytest.raises(Exception) as exc_info:
        run_pipeline(sample_input, state)

    assert exc_info.value.status_code == 503


def test_run_pipeline_calls_similarity_search_with_k(sample_input):
    docs = [_make_mock_doc()]
    state = _make_state(docs)

    run_pipeline(sample_input, state)

    state.vectorstore.similarity_search.assert_called_once()
    call_args = state.vectorstore.similarity_search.call_args
    assert call_args.kwargs.get("k") == settings.top_k_chunks
