import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest
from prometheus_client import REGISTRY

from app.config import settings
from app.main import _check_groq_model, _make_groq_client
from app.models import QuestionnaireInput
from app.rag import _content_to_text, run_pipeline


def _settings(**overrides):
    s = MagicMock()
    s.groq_api_key = "k"
    s.groq_timeout = 30
    s.groq_temperature = 0.0
    s.groq_max_tokens = 8000
    s.groq_reasoning_effort = "low"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def test_make_groq_client_sends_reasoning_effort_for_gpt_oss():
    with patch("app.main.ChatGroq") as cls, patch("app.main.settings", _settings()):
        _make_groq_client("openai/gpt-oss-120b")
    kwargs = cls.call_args.kwargs
    assert kwargs["model_name"] == "openai/gpt-oss-120b"
    assert kwargs["reasoning_effort"] == "low"
    assert kwargs["max_tokens"] == 8000
    assert kwargs["temperature"] == 0.0


def test_make_groq_client_omits_reasoning_effort_for_other_models():
    with patch("app.main.ChatGroq") as cls, patch("app.main.settings", _settings()):
        _make_groq_client("qwen/qwen3.6-27b")
    assert "reasoning_effort" not in cls.call_args.kwargs


def test_make_groq_client_omits_reasoning_effort_when_empty():
    with (
        patch("app.main.ChatGroq") as cls,
        patch("app.main.settings", _settings(groq_reasoning_effort="")),
    ):
        _make_groq_client("openai/gpt-oss-120b")
    assert "reasoning_effort" not in cls.call_args.kwargs


def test_check_groq_model_200_is_available():
    with patch("app.main.httpx.get", return_value=MagicMock(status_code=200)):
        assert _check_groq_model("k", "openai/gpt-oss-120b") is True


def test_check_groq_model_404_is_not_available(caplog):
    with patch("app.main.httpx.get", return_value=MagicMock(status_code=404)):
        assert (
            _check_groq_model("k", "meta-llama/llama-4-scout-17b-16e-instruct") is False
        )
    assert "NOT available" in caplog.text
    assert "deprecations" in caplog.text


def test_check_groq_model_network_error_is_inconclusive():
    with patch("app.main.httpx.get", side_effect=httpx.ConnectError("boom")):
        assert _check_groq_model("k", "openai/gpt-oss-120b") is None


def test_check_groq_model_other_status_is_inconclusive():
    with patch("app.main.httpx.get", return_value=MagicMock(status_code=401)):
        assert _check_groq_model("bad-key", "openai/gpt-oss-120b") is None


def _input():
    return QuestionnaireInput(
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


def _doc(source="RGPD.pdf"):
    d = MagicMock()
    d.page_content = f"Contenido de {source}"
    d.metadata = {"source": source}
    return d


def _state(primary_content="Respuesta principal"):
    state = MagicMock()
    state.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (_doc(), 0.85),
        (_doc(), 0.80),
    ]
    state.groq_client.invoke.return_value = MagicMock(content=primary_content)
    state.groq_fallback_client = MagicMock()
    state.groq_fallback_client.invoke.return_value = MagicMock(
        content="Respuesta del respaldo"
    )
    state.indexed_normativas = frozenset({"RGPD"})
    state.corpus_version = "v1"
    return state


def _metric(name, **labels):
    for metric in REGISTRY.collect():
        for sample in metric.samples:
            if sample.name == name and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                return sample.value
    return 0.0


def test_primary_success_reports_primary_model(mock_reranker):
    result = asyncio.run(run_pipeline(_input(), _state()))
    assert result.respuesta_completa.startswith("Respuesta principal")
    assert result.llm_model == settings.groq_model


def test_fallback_used_when_primary_fails(mock_reranker, caplog):
    state = _state()
    state.groq_client.invoke.side_effect = Exception("model_decommissioned")
    before = _metric("legaldev_llm_fallback_total", reason="Exception")
    result = asyncio.run(run_pipeline(_input(), state))
    assert result.respuesta_completa.startswith("Respuesta del respaldo")
    assert result.llm_model == settings.groq_fallback_model
    assert _metric("legaldev_llm_fallback_total", reason="Exception") == before + 1
    assert '"event": "llm_fallback"' in caplog.text


def test_503_when_both_models_fail(mock_reranker):
    state = _state()
    state.groq_client.invoke.side_effect = Exception("down")
    state.groq_fallback_client.invoke.side_effect = Exception("also down")
    with pytest.raises(Exception) as exc_info:
        asyncio.run(run_pipeline(_input(), state))
    assert exc_info.value.status_code == 503


def test_503_when_no_fallback_configured(mock_reranker):
    state = _state()
    state.groq_client.invoke.side_effect = Exception("down")
    state.groq_fallback_client = None
    with pytest.raises(Exception) as exc_info:
        asyncio.run(run_pipeline(_input(), state))
    assert exc_info.value.status_code == 503


def test_content_to_text_accepts_str_and_blocks():
    assert _content_to_text("hola") == "hola"
    blocks = [
        {"type": "reasoning", "reasoning": "pensando"},
        {"type": "text", "text": "hola "},
        "mundo",
    ]
    assert _content_to_text(blocks) == "hola mundo"
