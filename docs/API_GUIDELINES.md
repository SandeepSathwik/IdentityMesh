# API Guidelines

## Goals
APIs should be predictable, typed, auditable, and safe.

## General principles
- explicit versioning for public APIs
- stable resource identifiers
- structured errors
- request IDs
- pagination
- validation
- no secret values in responses
- least information needed

## Error shape
Suggested:

```json
{
  "error": {
    "code": "POLICY_EVALUATION_FAILED",
    "message": "Authorization decision could not be completed.",
    "request_id": "..."
  }
}
```

## Current endpoints

The pre-alpha API exposes public operational health and dashboard routes:

- `GET /health/live` — process liveness
- `GET /health/ready` — authenticated PostgreSQL and Neo4j dependency readiness
- `GET /` — data-free static identity dashboard shell

Readiness returns `503` if a required dependency cannot be verified. Responses expose service
state but never credentials or connection strings.

The following `/api/v1` routes require `Authorization: Bearer <configured token>`:

- `POST /api/v1/collections/aws/iam/roles` — synchronously collect, persist, project, verify,
  and promote one controlled-account role snapshot
- `GET /api/v1/snapshots` — bounded newest-first lifecycle history
- `GET /api/v1/snapshots/active` — authoritative active ready snapshot
- `GET /api/v1/principals` — cursor-paginated normalized principals from the exact active graph
- `GET /api/v1/graph` — basic role-node graph view; relationships are intentionally empty

The collection route accepts no credentials or account selector. AWS credentials come only
from the standard provider chain, and the verified caller must match the configured account.
Expected partial/provider outcomes return a terminal versioned run document; malformed,
unauthenticated, unavailable, and concurrent requests use the standard error envelope.
This single-token baseline is restricted by configuration validation to local and test
environments; non-local deployment requires a future reviewed authentication design and TLS.

## Authorization endpoint
A conceptual request:

```json
{
  "principal": "...",
  "acting_principal": "...",
  "delegation_chain": [],
  "action": "...",
  "resource": "...",
  "context": {}
}
```

Conceptual response:

```json
{
  "decision": "DENY",
  "reason_code": "DELEGATION_SCOPE_EXCEEDED",
  "policy": {
    "id": "...",
    "version": "..."
  },
  "audit_id": "...",
  "explanation": "..."
}
```

## Security
- authenticate sensitive endpoints
- authorize admin/configuration actions
- validate graph query inputs
- avoid raw query execution from clients
- rate-limit where useful
- avoid leaking internal stack traces

## Idempotency
Use idempotency for:
- collection triggers
- approval decisions
- high-impact writes
where duplicate execution could matter.

## Open choices
- REST versus selected RPC/event interfaces
- pagination style
- webhook formats
- SDK generation
- long-running job patterns
