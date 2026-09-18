# Failure Modes and Safe Behavior

## Objective
Define what should happen when dependencies or assumptions fail.

## AWS unavailable
Behavior:
- collection attempt returns `failed` with a stable reason code and safe message
- no roles are emitted from an attempt that cannot establish caller identity
- previous snapshot remains intact
- UI shows staleness
- no claim that missing identities were deleted

## Partial AWS permissions
Behavior:
- successful data retained
- missing API capabilities represented as bounded collection gaps
- collection attempt labeled `partial`
- findings that depend on missing evidence may be downgraded or suppressed according to explicit logic

The current role collector preserves valid roles from earlier pages when a later page fails.
If no valid roles remain after an IAM failure, the attempt is `failed`, not `partial`. A
successful empty response is `complete`; it is not interchangeable with unavailable data.

Collector attempt status and persisted snapshot status are separate concepts. Orchestration
maps a `complete` attempt to `collected`; `partial` and `failed` attempts are retained but map
to terminal snapshot failure with `AWS_COLLECTION_PARTIAL` or `AWS_COLLECTION_FAILED`.
Unexpected collector or contract failures are recorded as `AWS_COLLECTION_INTERNAL_ERROR`.
None of these failure paths activates the snapshot or displaces the prior active snapshot.

The AWS role normalizer accepts only validated role evidence. It preserves source provenance,
does not convert trust-policy text into an access conclusion, and reports provider fields
deferred from the principal contract. Invalid or unavailable provider data must not produce a
normalized principal.

Orchestrated persistence uses one PostgreSQL transaction for the collection attempt, gaps,
evidence, principals, and collection-stage snapshot transition. A constraint failure rolls
back all writes. Exact retries are idempotent; a retry with different content for the same snapshot returns
`COLLECTION_PERSISTENCE_CONFLICT`. Evidence cannot be written to a missing, non-collecting, or
collector-version-mismatched snapshot. If collection fails before persistence, orchestration
best-effort records a safe terminal failure; inability to record that failure is surfaced as
`AWS_COLLECTION_FAILURE_RECORDING_FAILED` rather than reported as success.

## Kubernetes unavailable
Same general pattern as provider failure.

## Neo4j unavailable
- API should not fabricate graph results
- graph-dependent analysis should fail clearly
- collection may continue if relational staging supports it
- runtime policy should not blindly allow due to graph unavailability

The implemented role pipeline advances complete evidence to `projecting`, then records a safe
terminal graph failure if Neo4j writing or exact digest verification fails. The prior active
snapshot remains available. A committed but unpromoted graph can be rebuilt idempotently from
PostgreSQL; it is never exposed merely because Neo4j contains nodes.

## Concurrent AWS collection
Only one API-triggered role pipeline may hold the PostgreSQL advisory lock. A competing trigger
returns `AWS_COLLECTION_ALREADY_RUNNING` and does not create another snapshot.

## Wrong AWS account
The caller account verified by STS must match `IDENTITYMESH_AWS_ALLOWED_ACCOUNT_ID` before IAM
listing begins. A mismatch returns `AWS_ACCOUNT_NOT_ALLOWED` with no role evidence.

## PostgreSQL unavailable
- writes fail safely
- runtime behavior depends on documented critical dependencies
- avoid accepting actions that cannot be audited if audit is mandatory

## Policy engine unavailable
Default for sensitive actions:
`DENY` or equivalent fail-closed result.

A configurable fail-open mode, if ever implemented, must be restricted and explicit.

## Telemetry exporter unavailable
- authorization decision remains authoritative
- event should be queued/retried where practical
- failure surfaced in health status

## Stale graph
Runtime decision must know graph freshness if graph-derived context is used.

Possible behavior:
- deny critical actions
- require approval
- use policy-only decision for low-risk paths
depending on documented configuration

## Unknown principal
Do not silently map to a trusted default.

## Unknown action/resource
Default should be conservative.

## Malformed delegation
Reject.

## Expired delegation
Reject.

## Missing parent delegation
Reject or require re-authentication.

## Approval service unavailable
Do not convert `REQUIRE_APPROVAL` to `ALLOW`.

## LLM unavailable
Core discovery, graph, attack-path, and authorization should continue without LLM features.

## LLM returns invalid content
Discard or label as failed advisory output.

## Migration failure
- stop startup if schema is unsafe
- do not partially reinterpret old data
- provide clear recovery guidance

The current Compose topology enforces this by gating API startup on successful completion of a
one-shot Alembic migration service.

## Cloud lab teardown failure
- surface remaining resources
- provide manual cleanup instructions
- preserve cost visibility
