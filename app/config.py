from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    groq_api_key: str
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    chroma_db_path: str = "./chroma_db"
    docs_path: str = "./docs"
    top_k_chunks: int = 8


settings = Settings()
