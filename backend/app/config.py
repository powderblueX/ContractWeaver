"""Typed configuration loaded from environment or a local untracked .env."""

import os
from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


def default_database_path() -> Path:
    """Use the new name for clean installs without abandoning existing data."""
    current = BASE_DIR / "data" / "contractweaver.db"
    previous = BASE_DIR / "data" / "lawreasoner.db"
    return previous if previous.is_file() and not current.exists() else current


class Settings(BaseSettings):
    """One source of truth for runtime paths, provider details and limits."""

    model_config = SettingsConfigDict(
        env_prefix="LAW_",
        env_file=Path(os.environ.get("LAW_ENV_FILE", str(BASE_DIR / ".env"))),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    database_path: Path = Field(default_factory=default_database_path)
    resources_dir: Path = BASE_DIR / "resources" / "contracts"
    generated_dir: Path = BASE_DIR / "data" / "generated"
    cors_origins_csv: str = Field("http://localhost:5173", validation_alias="LAW_CORS_ORIGINS")
    llm_base_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_json_mode: Literal["json_object", "json_schema", "prompt"] = "json_object"
    llm_thinking_mode: Literal["provider_default", "enabled", "disabled"] = "provider_default"
    llm_reasoning_effort: Literal["provider_default", "low", "high", "max"] = "provider_default"
    harness_max_requests: int = Field(512, ge=1, le=2000)
    harness_max_steps: int = Field(512, ge=2, le=2000)
    harness_timeout_seconds: float = Field(3600, ge=10, le=14400)
    harness_max_input_chars: int = Field(500000, ge=10000, le=2000000)
    llm_max_tokens: int = Field(8192, ge=256, le=131072)
    llm_temperature: float = Field(0.2, ge=0, le=2)
    structured_output_retries: int = Field(1, ge=0, le=2)
    max_source_chars: int = Field(60000, ge=1000, le=300000)
    max_upload_bytes: int = Field(5 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    fields_per_batch: int = Field(30, ge=5, le=80)
    agent_parallelism: int = Field(2, ge=1, le=4)
    supervisor_max_searches: int = Field(3, ge=1, le=5)
    supervisor_max_repairs: int = Field(1, ge=0, le=2)
    coverage_max_context_chars: int = Field(120000, ge=10000, le=1000000)
    recommendation_limit: int = Field(5, ge=1, le=10)
    retrieval_candidate_pool: int = Field(30, ge=5, le=100)
    retrieval_bm25_k1: float = Field(1.5, gt=0, le=5)
    retrieval_bm25_b: float = Field(0.75, ge=0, le=1)
    retrieval_rrf_constant: int = Field(60, ge=1, le=1000)
    token_hours: int = Field(24, ge=1, le=720)
    request_timeout: float = Field(90, ge=5, le=300)
    embedding_model_path: Path | None = None

    @field_validator("database_path", "resources_dir", "generated_dir", "embedding_model_path", mode="after")
    @classmethod
    def resolve_path(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        expanded = value.expanduser()
        return (expanded if expanded.is_absolute() else BASE_DIR / expanded).resolve()

    @field_validator("llm_base_url")
    @classmethod
    def normalize_url(cls, value: str) -> str:
        base_url = value.strip().rstrip("/")
        if not base_url:
            return ""
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in ("https", "http")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("LAW_LLM_BASE_URL 必须是无账号、查询参数的 HTTP(S) 基础地址")
        if parsed.path.endswith("/chat/completions"):
            raise ValueError("LAW_LLM_BASE_URL 填基础地址，不要包含 /chat/completions")
        try:
            is_loopback = ip_address(parsed.hostname).is_loopback
        except ValueError:
            is_loopback = parsed.hostname == "localhost"
        if parsed.scheme != "https" and not is_loopback:
            raise ValueError("远程模型地址必须使用 HTTPS，以免泄露 API 密钥")
        return base_url

    @field_validator("llm_model")
    @classmethod
    def normalize_model_name(cls, value: str) -> str:
        model_name = value.strip()
        return model_name

    @property
    def model_configured(self) -> bool:
        """Only expose readiness, never the credential itself."""
        return not self.missing_model_settings

    @property
    def missing_model_settings(self) -> list[str]:
        values = {
            "LAW_LLM_API_KEY": self.llm_api_key.get_secret_value().strip(),
            "LAW_LLM_BASE_URL": self.llm_base_url,
            "LAW_LLM_MODEL": self.llm_model,
        }
        return [name for name, value in values.items() if not value]

    @property
    def cors_origins(self) -> tuple[str, ...]:
        return tuple(origin.strip() for origin in self.cors_origins_csv.split(",") if origin.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
