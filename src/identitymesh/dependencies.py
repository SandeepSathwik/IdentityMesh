"""External dependency readiness probes."""

from collections.abc import Mapping

import asyncpg  # type: ignore[import-untyped]
from neo4j import AsyncGraphDatabase

from identitymesh.config import Settings
from identitymesh.health import DependencyProbe


class PostgresReadinessProbe:
    """Verify authenticated PostgreSQL query access."""

    def __init__(self, dsn: str, timeout_seconds: float) -> None:
        self._dsn = dsn
        self._timeout_seconds = timeout_seconds

    async def __call__(self) -> bool:
        connection = await asyncpg.connect(dsn=self._dsn, timeout=self._timeout_seconds)
        try:
            result = await connection.fetchval("SELECT 1")
            return bool(result == 1)
        finally:
            await connection.close(timeout=self._timeout_seconds)


class Neo4jReadinessProbe:
    """Verify authenticated Neo4j connectivity."""

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        timeout_seconds: float,
    ) -> None:
        self._uri = uri
        self._auth = (username, password)
        self._timeout_seconds = timeout_seconds

    async def __call__(self) -> bool:
        driver = AsyncGraphDatabase.driver(
            self._uri,
            auth=self._auth,
            connection_timeout=self._timeout_seconds,
        )
        try:
            await driver.verify_connectivity()
            return True
        finally:
            await driver.close()


def build_readiness_probes(settings: Settings) -> Mapping[str, DependencyProbe]:
    """Build probes only for explicitly configured dependencies."""

    probes: dict[str, DependencyProbe] = {}

    if settings.postgres_dsn is not None:
        probes["postgresql"] = PostgresReadinessProbe(
            dsn=settings.postgres_dsn.get_secret_value(),
            timeout_seconds=settings.dependency_timeout_seconds,
        )

    if (
        settings.neo4j_uri is not None
        and settings.neo4j_username is not None
        and settings.neo4j_password is not None
    ):
        probes["neo4j"] = Neo4jReadinessProbe(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password.get_secret_value(),
            timeout_seconds=settings.dependency_timeout_seconds,
        )

    return probes
