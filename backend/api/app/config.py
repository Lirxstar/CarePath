import logging
from functools import lru_cache
from os import getenv
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE_VARIABLE = "CAREPATH_ENV_FILE"
EnvironmentName = Literal["development", "test", "production"]
PrivacyMode = Literal["standard_demo", "local_strict"]
LocalStructuredOutputMode = Literal["openai_json_schema", "vllm_json"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CAREPATH_",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
    )

    app_name: str = Field(default="CarePath API", min_length=1)
    environment: EnvironmentName = "development"
    privacy_mode: PrivacyMode = "standard_demo"
    log_level: str = "INFO"
    request_id_header: str = Field(
        default="X-Request-ID",
        pattern=r"^[A-Za-z0-9-]+$",
    )
    request_id_max_length: int = Field(default=128, ge=16, le=256)
    llm_provider: str = "mock"
    llm_api_key: SecretStr | None = None

    local_llm_base_url: str = "http://127.0.0.1:8000"
    local_llm_model_id: str = Field(default="carepath-local", min_length=1)
    local_llm_structured_output_mode: LocalStructuredOutputMode = "openai_json_schema"
    local_llm_request_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    local_llm_max_new_tokens: int = Field(default=512, ge=1, le=4096)
    local_llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    database_url: str = Field(default="sqlite:///./carepath.db", min_length=1)
    evidence_index_path: str = Field(default="data/guidelines/qdrant", min_length=1)
    evidence_collection_name: str = Field(
        default="carepath_guidelines_cp007_v1",
        min_length=1,
    )
    evidence_embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        min_length=1,
    )
    reviewer_web_dir: str | None = None

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in logging.getLevelNamesMapping():
            raise ValueError(f"Unsupported log level: {value}")
        return normalized

    @field_validator("llm_provider")
    @classmethod
    def normalize_provider_name(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("LLM provider name must not be empty")
        return normalized

    @field_validator(
        "database_url",
        "evidence_index_path",
        "evidence_collection_name",
        "evidence_embedding_model",
        "local_llm_model_id",
    )
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("configuration value must not be empty")
        return normalized

    @field_validator("reviewer_web_dir")
    @classmethod
    def normalize_optional_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("local_llm_base_url")
    @classmethod
    def validate_local_llm_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("local_llm_base_url must be a credential-free loopback HTTP origin")
        return normalized

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        supported_prefixes = (
            "sqlite://",
            "postgresql://",
            "postgresql+psycopg://",
            "postgres://",
        )
        if not value.startswith(supported_prefixes):
            raise ValueError("database_url must use SQLite or PostgreSQL")
        return value


@lru_cache
def get_settings() -> Settings:
    env_file = getenv(ENV_FILE_VARIABLE)
    # BaseSettings accepts this runtime option, but its synthesized constructor omits it.
    return Settings(_env_file=env_file or None)  # type: ignore[call-arg]
