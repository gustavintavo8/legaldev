from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": stale/unknown keys in a user's .env (e.g. a renamed setting)
    # must never crash startup — os.environ unknowns were already ignored.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    groq_api_key: str
    groq_model: str = "openai/gpt-oss-120b"
    # Segundo modelo si el principal falla (retirado, 429, 5xx). "" lo desactiva.
    groq_fallback_model: str = "openai/gpt-oss-20b"
    # Solo se envía a modelos openai/gpt-oss*. "" no envía el parámetro.
    groq_reasoning_effort: str = "low"
    groq_verify_model_on_startup: bool = True
    chroma_db_path: str = "./chroma_db"
    docs_path: str = "./docs"
    top_k_chunks: int = 12
    cookies_k: int = 6
    colegiado_k: int = 6
    rgpd_k: int = 6
    overfetch_k: int = 100
    reranker_top_k: int = 25
    # Máximo de chunks de una misma normativa en el top-k del reranker (0 desactiva).
    max_chunks_per_source: int = 4
    groq_timeout: int = 30
    groq_temperature: float = 0.0
    groq_max_tokens: int = 8000
    min_relevance_score: float = 0.40
    rate_limit: str = "10/minute"
    allowed_origins: str = "*"
    trust_proxy_headers: bool = False
    # Timeout global de la fase de retrieval (búsquedas Chroma + reranker CPU), en segundos.
    retrieval_timeout: float = 60.0
    log_level: str = "INFO"
    api_keys: str = ""

    @property
    def api_key_set(self) -> frozenset[str]:
        if not self.api_keys.strip():
            return frozenset()
        return frozenset(k.strip() for k in self.api_keys.split(",") if k.strip())

    @field_validator("allowed_origins")
    @classmethod
    def validate_allowed_origins(cls, v: str) -> str:
        parts = [p.strip() for p in v.split(",")]
        if "*" in parts and len(parts) > 1:
            raise ValueError(
                f"ALLOWED_ORIGINS: '*' must be the only value when present, got: {v!r}"
            )
        return v

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()
