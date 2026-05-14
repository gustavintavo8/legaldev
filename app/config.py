from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    groq_api_key: str
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    chroma_db_path: str = "./chroma_db"
    docs_path: str = "./docs"
    top_k_chunks: int = 12
    cookies_k: int = 6
    colegiado_k: int = 6
    rgpd_k: int = 6
    overfetch_k: int = 100
    groq_timeout: int = 30
    groq_temperature: float = 0.0
    groq_max_tokens: int = 4000
    min_relevance_score: float = 0.35
    rate_limit: str = "10/minute"
    allowed_origins: str = "*"
    trust_proxy_headers: bool = False
    chroma_timeout: float = 10.0

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
