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
    overfetch_k: int = 100
    groq_timeout: int = 30
    groq_temperature: float = 0.0
    groq_max_tokens: int = 4000
    min_relevance_score: float = 0.35
    rate_limit: str = "10/minute"
    allowed_origins: str = "*"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()
