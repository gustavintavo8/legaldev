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
