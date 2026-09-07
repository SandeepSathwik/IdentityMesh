# Failure Modes and Safe Behavior

## Objective
Define what should happen when dependencies or assumptions fail.

## AWS unavailable
Behavior:
- collection marked failed
- previous snapshot remains intact
- UI shows staleness
- no claim that missing identities were deleted

## Partial AWS permissions
Behavior:
- successful data retained
- missing API capabilities listed
- snapshot labeled incomplete
- findings that depend on missing evidence may be downgraded or suppressed according to explicit logic

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

## Cloud lab teardown failure
- surface remaining resources
- provide manual cleanup instructions
- preserve cost visibility
