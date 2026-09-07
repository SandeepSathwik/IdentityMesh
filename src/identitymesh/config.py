"""Validated application configuration."""

from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """IdentityMesh settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="IDENTITYMESH_",
        extra="forbid",
        case_sensitive=False,
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    dependency_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    postgres_dsn: SecretStr | None = None
    neo4j_uri: str | None = None
    neo4j_username: str | None = None
    neo4j_password: SecretStr | None = None

    @field_validator("postgres_dsn")
    @classmethod
    def validate_postgres_dsn(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None

        dsn = value.get_secret_value()
        if not dsn.startswith(("postgresql://", "postgres://")):
            raise ValueError("postgres_dsn must use the PostgreSQL URI scheme")
        return value

    @field_validator("neo4j_uri")
    @classmethod
    def validate_neo4j_uri(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("neo4j://", "neo4j+s://", "bolt://", "bolt+s://")):
            raise ValueError("neo4j_uri must use a supported Neo4j URI scheme")
        return value

    @model_validator(mode="after")
    def validate_neo4j_configuration(self) -> "Settings":
        configured = (self.neo4j_uri, self.neo4j_username, self.neo4j_password)
        if any(value is not None for value in configured) and not all(
            value is not None for value in configured
        ):
            raise ValueError("Neo4j URI, username, and password must be configured together")
        return self
