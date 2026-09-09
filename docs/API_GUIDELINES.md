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

The pre-alpha API currently exposes only operational health endpoints:

- `GET /health/live` — process liveness
- `GET /health/ready` — authenticated PostgreSQL and Neo4j dependency readiness

Readiness returns `503` if a required dependency cannot be verified. Responses expose service
state but never credentials or connection strings. Collector, snapshot, graph, and
authorization endpoints are not yet public APIs.

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
