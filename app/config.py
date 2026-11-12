import limits
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_MCP_DAILY_LIMIT_FORMAT = "MCP_DAILY_LIMIT es un tope diario: «N/day» (p. ej. «200/day») o «N»; vacío o 0, sin tope"


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
    # Servidor MCP en POST /mcp (app/mcp_server.py). Solo se monta si hay claves para él
    # (RNF-15: /mcp exige siempre clave; 22-arquitectura, «Despliegue»).
    mcp_enabled: bool = False
    # Claves propias de /mcp. Si está vacía, /mcp usa API_KEYS. Sirve para desplegar con la web
    # pública, que llama a /v1/analyze sin clave: API_KEYS vacía y /mcp con sus claves.
    mcp_api_keys: str = ""
    # Orígenes de navegador admitidos en /mcp (RNF-18, protección frente a DNS rebinding),
    # separados por comas. Independiente de ALLOWED_ORIGINS (CORS de la web): los clientes MCP
    # de escritorio no envían Origin, así que la lista vacía solo rechaza a los navegadores.
    mcp_allowed_origins: str = ""
    # Tope diario de analizar_proyecto por clave en /mcp (modelo de amenazas: una clave filtrada
    # no puede agotar la cuota de Groq). «200/day» o «200»; vacío o 0, sin tope. Se suma al
    # cupo por minuto de RATE_LIMIT y usa el mismo almacén (app/mcp_guard.py).
    mcp_daily_limit: str = ""

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

    @field_validator("mcp_allowed_origins")
    @classmethod
    def validate_mcp_allowed_origins(cls, v: str) -> str:
        if "*" in (p.strip() for p in v.split(",")):
            raise ValueError(
                "MCP_ALLOWED_ORIGINS no admite '*': la validación de Origin no protegería de nada"
            )
        return v

    @field_validator("mcp_daily_limit")
    @classmethod
    def validate_mcp_daily_limit(cls, v: str) -> str:
        """Forma normal «N/day», o «» sin tope (vacío, «0» o «0/day»).

        Un valor que no sea un único límite por día falla al arrancar, como las listas de
        orígenes: «200/hour» no es un tope diario y «1/day;2/day» no se puede leer como uno.
        """
        v = v.strip()
        if v.isdigit():
            v = f"{v}/day"
        if not v:
            return ""
        try:
            items = limits.parse_many(v)
        except ValueError:
            raise ValueError(f"{_MCP_DAILY_LIMIT_FORMAT}; recibido {v!r}") from None
        if len(items) != 1:
            raise ValueError(f"{_MCP_DAILY_LIMIT_FORMAT}; recibido {v!r}")
        item = items[0]
        if not isinstance(item, limits.RateLimitItemPerDay) or item.multiples != 1:
            raise ValueError(f"{_MCP_DAILY_LIMIT_FORMAT}; recibido {v!r}")
        return f"{item.amount}/day" if item.amount else ""

    @property
    def mcp_daily_limit_item(self) -> limits.RateLimitItem | None:
        """El tope diario como límite de ``limits``, o ``None`` si no hay tope."""
        return limits.parse(self.mcp_daily_limit) if self.mcp_daily_limit else None

    @property
    def mcp_key_set(self) -> frozenset[str]:
        """Claves que abren /mcp: MCP_API_KEYS si existe; si no, las de API_KEYS."""
        propias = frozenset(
            k.strip() for k in self.mcp_api_keys.split(",") if k.strip()
        )
        return propias or self.api_key_set

    @property
    def mcp_origin_set(self) -> frozenset[str]:
        return frozenset(
            o.strip().rstrip("/")
            for o in self.mcp_allowed_origins.split(",")
            if o.strip()
        )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()
