from unittest.mock import MagicMock, patch

import httpx

from app.main import _check_groq_model, _make_groq_client


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
