from functools import lru_cache
from typing import Any, Literal, Optional
from pydantic import Field, PostgresDsn, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Production Application Configuration for BrandShield AI.
    Adheres to 12-factor application methodology and Pydantic v2 Settings.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

    # Environment
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    PROJECT_NAME: str = "BrandShield AI"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # Security & JWT
    SECRET_KEY: str = Field(
        default="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7",
        description="Cryptographically secure secret key for JWT signing"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    HASH_CHAIN_SALT: str = Field(
        default="b5a8370d9e2948bb8f0b7305988147d3",
        description="Salt utilized for immutable Merkle audit hash chain calculation"
    )

    # Database & Pool Settings (PostgreSQL 16+ with pgvector)
    DATABASE_URL: str | None = Field(
        default=None,
        description="Full connection string (e.g. from Render or Heroku environment)"
    )
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "brandshield_ai"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: float = 30.0
    DB_POOL_RECYCLE: int = 1800  # 30 minutes
    DB_ECHO: bool = False

    @computed_field  # type: ignore[misc]
    @property
    def ASYNC_DATABASE_URL(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # CORS & Frontend Origins
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    CORS_ALLOW_ORIGIN_REGEX: str = r"^https://(.*\.vercel\.app|.*\.onrender\.com)$"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        default_dev = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
        if isinstance(v, str):
            v_str = v.strip()
            if v_str.startswith("[") and v_str.endswith("]"):
                import json
                try:
                    items = json.loads(v_str)
                    parsed = [str(x).strip().rstrip("/") for x in items if str(x).strip()]
                    return list(dict.fromkeys(parsed + default_dev))
                except Exception:
                    pass
            parsed = [x.strip().rstrip("/") for x in v.split(",") if x.strip()]
            return list(dict.fromkeys(parsed + default_dev))
        elif isinstance(v, (list, tuple)):
            parsed = [str(x).strip().rstrip("/") for x in v if str(x).strip()]
            return list(dict.fromkeys(parsed + default_dev))
        return default_dev

    # Redis Cache & Token Bucket Rate Limiting
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL_SECONDS: int = 3600

    # RAG & Embeddings
    EMBEDDING_DIMENSION: int = 1536
    RRF_K_PARAMETER: int = 60
    VECTOR_SIMILARITY_THRESHOLD: float = 0.82

    # Privacy Gate & Safeguards
    AUTOMATION_BIAS_SAMPLE_RATE: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Sampling rate (default 15%) to inject shadow audits and combat human automation bias"
    )
    STOCHASTIC_AUDIT_PROBABILITY: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Pseudo-random sampling fraction (15%) to inject shadow audits and combat human automation bias"
    )
    DEMO_MODE: bool = Field(
        default=True,
        description="When true, enables high-reliability instant demo mode with verified fallback examples"
    )
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_TIME: int = 30  # seconds
    EXTERNAL_LLM_TIMEOUT_SECONDS: float = 0.5  # 500ms strict SLA watchdog
    OPENAI_API_KEY: Optional[str] = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns cached singleton application settings instance."""
    return Settings()
