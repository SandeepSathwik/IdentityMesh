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

    data_api_enabled: bool = False
    api_token: SecretStr | None = None
    aws_allowed_account_id: str | None = None

    postgres_dsn: SecretStr | None = None
    neo4j_uri: str | None = None
    neo4j_username: str | None = None
    neo4j_password: SecretStr | None = None
    neo4j_database: str = Field(default="neo4j", min_length=1, max_length=64)

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

    @field_validator("api_token")
    @classmethod
    def validate_api_token(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        token = value.get_secret_value()
        invalid = (
            len(token) < 32
            or len(token) > 256
            or not token.isascii()
            or not token.isprintable()
            or any(character.isspace() for character in token)
        )
        if invalid:
            raise ValueError(
                "api_token must contain 32 to 256 printable non-whitespace ASCII characters"
            )
        return value

    @field_validator("aws_allowed_account_id")
    @classmethod
    def validate_aws_account_id(cls, value: str | None) -> str | None:
        if value is not None and (len(value) != 12 or not value.isdigit()):
            raise ValueError("aws_allowed_account_id must be a 12-digit AWS account ID")
        return value

    @model_validator(mode="after")
    def validate_neo4j_configuration(self) -> "Settings":
        configured = (self.neo4j_uri, self.neo4j_username, self.neo4j_password)
        if any(value is not None for value in configured) and not all(
            value is not None for value in configured
        ):
            raise ValueError("Neo4j URI, username, and password must be configured together")
        if self.data_api_enabled:
            if self.environment not in {"local", "test"}:
                raise ValueError(
                    "the bearer-token data API is limited to local and test environments"
                )
            required = {
                "api_token": self.api_token,
                "aws_allowed_account_id": self.aws_allowed_account_id,
                "postgres_dsn": self.postgres_dsn,
                "neo4j_uri": self.neo4j_uri,
                "neo4j_username": self.neo4j_username,
                "neo4j_password": self.neo4j_password,
            }
            missing = sorted(name for name, value in required.items() if value is None)
            if missing:
                raise ValueError(
                    "data API requires complete secure configuration: " + ", ".join(missing)
                )
        return self
