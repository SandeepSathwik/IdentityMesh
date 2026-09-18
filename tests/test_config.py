"""Configuration validation tests."""

import pytest
from pydantic import ValidationError

from identitymesh.config import Settings


def test_settings_use_safe_local_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "local"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000


def test_settings_reject_unknown_environment() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="qa", _env_file=None)  # type: ignore[arg-type]


@pytest.mark.parametrize("port", [0, 65536])
def test_settings_reject_invalid_port(port: int) -> None:
    with pytest.raises(ValidationError):
        Settings(api_port=port, _env_file=None)


def test_settings_reject_non_postgresql_dsn() -> None:
    with pytest.raises(ValidationError):
        Settings(postgres_dsn="https://example.test", _env_file=None)  # type: ignore[arg-type]


def test_settings_reject_partial_neo4j_configuration() -> None:
    with pytest.raises(ValidationError):
        Settings(neo4j_uri="bolt://localhost:7687", _env_file=None)


def test_data_api_requires_complete_secure_configuration() -> None:
    with pytest.raises(ValidationError, match="data API requires complete secure configuration"):
        Settings(data_api_enabled=True, _env_file=None)


def test_data_api_accepts_complete_configuration() -> None:
    settings = Settings(
        data_api_enabled=True,
        api_token="a" * 32,
        aws_allowed_account_id="123456789012",
        postgres_dsn="postgresql://identitymesh:test@localhost/identitymesh",
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="test-only",  # noqa: S106 - synthetic test configuration
        _env_file=None,
    )

    assert settings.data_api_enabled is True
    assert settings.aws_allowed_account_id == "123456789012"


def test_data_api_rejects_nonlocal_deployment() -> None:
    with pytest.raises(ValidationError, match="limited to local and test"):
        Settings(
            environment="production",
            data_api_enabled=True,
            api_token="a" * 32,
            aws_allowed_account_id="123456789012",
            postgres_dsn="postgresql://identitymesh:test@localhost/identitymesh",
            neo4j_uri="bolt://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="test-only",  # noqa: S106 - synthetic test configuration
            _env_file=None,
        )


@pytest.mark.parametrize(
    "token",
    ["short", "x" * 257, "x" * 31 + "\n", "x" * 31 + " ", "é" * 32],
)
def test_settings_reject_unsafe_api_token(token: str) -> None:
    with pytest.raises(ValidationError, match="api_token"):
        Settings(api_token=token, _env_file=None)


@pytest.mark.parametrize("account_id", ["123", "12345678901x", " 123456789012"])
def test_settings_reject_invalid_allowed_account_id(account_id: str) -> None:
    with pytest.raises(ValidationError, match="aws_allowed_account_id"):
        Settings(aws_allowed_account_id=account_id, _env_file=None)
