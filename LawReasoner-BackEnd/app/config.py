"""Typed configuration loaded from environment or a local untracked .env."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """One source of truth for runtime paths, provider details and limits."""

    model_config = SettingsConfigDict(
        env_prefix="LAW_",
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    database_path: Path = BASE_DIR / "data" / "lawreasoner.db"
    resources_dir: Path = BASE_DIR / "resources" / "contracts"
    generated_dir: Path = BASE_DIR / "data" / "generated"
    law_data_path: Path = Field(BASE_DIR / "resources" / "law" / "minfadian.json", validation_alias="LAW_CIVIL_CODE_PATH")
    cors_origins_csv: str = Field("http://localhost:5173", validation_alias="LAW_CORS_ORIGINS")
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "qwen-plus"
    max_agent_steps: int = Field(5, ge=1, le=10)
    token_hours: int = Field(24, ge=1, le=720)
    request_timeout: float = Field(90, ge=5, le=300)
    embedding_model_path: Path | None = None

    @field_validator("database_path", "resources_dir", "generated_dir", "law_data_path", "embedding_model_path", mode="after")
    @classmethod
    def resolve_path(cls, value: Path | None) -> Path | None:
        return value.expanduser().resolve() if value else None

    @field_validator("llm_base_url")
    @classmethod
    def normalize_url(cls, value: str) -> str:
        if not value.startswith(("https://", "http://")):
            raise ValueError("模型地址必须以 http:// 或 https:// 开头")
        return value.rstrip("/")

    @property
    def cors_origins(self) -> tuple[str, ...]:
        return tuple(origin.strip() for origin in self.cors_origins_csv.split(",") if origin.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
