"""Dependency readiness construction tests."""

import asyncio
from unittest.mock import AsyncMock, Mock

from pydantic import SecretStr
from pytest import MonkeyPatch

from identitymesh.config import Settings
from identitymesh.dependencies import (
    Neo4jReadinessProbe,
    PostgresReadinessProbe,
    build_readiness_probes,
)


def test_no_probes_are_created_without_dependency_configuration() -> None:
    probes = build_readiness_probes(Settings(environment="test", _env_file=None))

    assert probes == {}


def test_configured_dependencies_create_named_probes() -> None:
    settings = Settings(
        environment="test",
        postgres_dsn=SecretStr("postgresql://user:password@localhost/database"),
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password=SecretStr("password"),
        _env_file=None,
    )

    probes = build_readiness_probes(settings)

    assert set(probes) == {"postgresql", "neo4j"}


def test_postgresql_probe_queries_and_closes_connection(monkeypatch: MonkeyPatch) -> None:
    connection = Mock()
    connection.fetchval = AsyncMock(return_value=1)
    connection.close = AsyncMock()
    connect = AsyncMock(return_value=connection)

    from identitymesh import dependencies

    monkeypatch.setattr(dependencies.asyncpg, "connect", connect)
    probe = PostgresReadinessProbe(
        "postgresql://user:password@localhost/database", timeout_seconds=1.0
    )

    assert asyncio.run(probe()) is True
    connection.fetchval.assert_awaited_once_with("SELECT 1")
    connection.close.assert_awaited_once_with(timeout=1.0)


def test_neo4j_probe_verifies_and_closes_driver(monkeypatch: MonkeyPatch) -> None:
    driver = Mock()
    driver.verify_connectivity = AsyncMock()
    driver.close = AsyncMock()
    test_value = "synthetic-test-value"

    from identitymesh import dependencies

    driver_factory = Mock(return_value=driver)
    monkeypatch.setattr(dependencies.AsyncGraphDatabase, "driver", driver_factory)
    probe = Neo4jReadinessProbe(
        "bolt://localhost:7687",
        username="neo4j",
        password=test_value,
        timeout_seconds=1.0,
    )

    assert asyncio.run(probe()) is True
    driver.verify_connectivity.assert_awaited_once_with()
    driver.close.assert_awaited_once_with()
