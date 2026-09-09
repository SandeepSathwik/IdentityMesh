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

Collector attempt status and persisted snapshot status are separate concepts. The integration
that maps collection results into snapshot transitions has not yet been implemented.

The AWS role normalizer accepts only validated role evidence. It preserves source provenance,
does not convert trust-policy text into an access conclusion, and reports provider fields
deferred from the principal contract. Invalid or unavailable provider data must not produce a
normalized principal.

## Kubernetes unavailable
Same general pattern as provider failure.

## Neo4j unavailable
- API should not fabricate graph results
- graph-dependent analysis should fail clearly
- collection may continue if relational staging supports it
- runtime policy should not blindly allow due to graph unavailability

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
