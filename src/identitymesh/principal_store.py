"""Read validated normalized principals from authoritative PostgreSQL evidence."""

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]
from pydantic import ValidationError

from identitymesh.principals import Principal


class PrincipalSourceError(Exception):
    """Raised when authoritative normalized records cannot be projected safely."""

    reason_code = "GRAPH_SOURCE_INVALID"


def _decode_principal(value: object) -> Principal:
    try:
        document = value if isinstance(value, str) else json.dumps(value)
        return Principal.model_validate_json(document)
    except (json.JSONDecodeError, TypeError, ValidationError) as error:
        raise PrincipalSourceError(
            "stored principal did not match its validated contract"
        ) from error


def _validate_row(row: Mapping[str, Any], snapshot_id: UUID) -> Principal:
    principal = _decode_principal(row["principal"])
    matches = (
        principal.provenance.snapshot_id == snapshot_id
        and principal.principal_id == row["principal_id"]
        and principal.provider == row["provider"]
        and principal.principal_type.value == row["principal_type"]
        and principal.external_id == row["external_id"]
        and principal.display_name == row["display_name"]
    )
    if not matches:
        raise PrincipalSourceError("stored principal columns did not match the principal document")
    return principal


class PrincipalStore:
    """Load an immutable snapshot's normalized principal documents."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def load_snapshot(self, snapshot_id: UUID) -> tuple[Principal, ...]:
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT principal_id, provider, principal_type, external_id,
                       display_name, principal
                FROM principals
                WHERE snapshot_id = $1
                ORDER BY principal_id
                """,
                snapshot_id,
            )
        return tuple(_validate_row(row, snapshot_id) for row in rows)
