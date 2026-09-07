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
