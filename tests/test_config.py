import pytest
from pydantic import ValidationError

from app.config import Settings


def test_allowed_origins_star_alone_is_valid():
    s = Settings(groq_api_key="x", allowed_origins="*")
    assert s.cors_origins == ["*"]


def test_allowed_origins_multiple_urls_valid():
    s = Settings(groq_api_key="x", allowed_origins="https://foo.com,https://bar.com")
    assert s.cors_origins == ["https://foo.com", "https://bar.com"]


def test_allowed_origins_star_combined_raises():
    with pytest.raises(ValidationError, match="must be the only value"):
        Settings(groq_api_key="x", allowed_origins="*,https://foo.com")


def test_allowed_origins_star_combined_reversed_raises():
    with pytest.raises(ValidationError, match="must be the only value"):
        Settings(groq_api_key="x", allowed_origins="https://foo.com,*")


def test_log_level_defaults_to_info():
    from app.config import settings

    assert settings.log_level.upper() == "INFO"


def test_log_level_env_var_is_read(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    from importlib import reload

    import app.config

    reload(app.config)
    assert app.config.settings.log_level.upper() == "DEBUG"
    # Reload back to default to avoid polluting other tests
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    reload(app.config)
