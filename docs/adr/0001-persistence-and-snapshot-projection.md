# ADR-0001: Persistence ownership and snapshot projection

## Status
Accepted

## Context
IdentityMesh needs relational operational state and graph-optimized analysis without allowing
the two databases to become competing sources of truth. Collection and graph projection can
fail independently, and V1 does not justify distributed transactions.

## Decision drivers
- preserve provider evidence
- reproducible findings
- explicit partial-failure behavior
- recoverable graph state
- operational simplicity

## Options considered

### Co-equal PostgreSQL and Neo4j writes
Both stores would be independently updated as facts arrive.

This provides low-latency graph updates but creates ambiguous ownership, partial-write states,
and difficult recovery.

### PostgreSQL authority with versioned Neo4j projections
PostgreSQL owns collected evidence, snapshot lifecycle, configuration, and the active snapshot
reference. Neo4j contains rebuildable projections keyed by snapshot and projection version.

This introduces a projection step but gives failures and recovery deterministic semantics.

## Decision
PostgreSQL is the authoritative operational and evidence store. Neo4j is a derived,
rebuildable graph projection.

A snapshot progresses through explicit states such as collection, projection, ready, and
failed. A new snapshot becomes active only after its graph projection is complete and verified.
Readers use only a matching ready snapshot and projection version. If collection or projection
fails, the prior ready snapshot remains active and its staleness remains visible.

No distributed transaction is introduced. Domain tables, retention periods, and projection
implementation details remain deferred until representative AWS evidence is available.

## Consequences

### Positive
- findings can be tied to immutable snapshot and rule versions
- Neo4j can be rebuilt without losing provider evidence
- projection failure cannot silently replace prior valid analysis
- ownership and recovery behavior are explicit

### Negative
- projections are not immediately consistent with newly collected evidence
- snapshot promotion requires validation and lifecycle state
- storage use may increase while multiple snapshots coexist

### Risks
- application queries could accidentally mix snapshot versions
- failed projections could accumulate without cleanup
- an incorrectly promoted snapshot could expose incomplete analysis

## Security implications
Every graph query and finding must carry a snapshot identifier. Partial or stale evidence must
remain visible. Promotion must fail safely, and projection errors must never be interpreted as
absence of identities or relationships.

Database credentials remain separate and least-privileged. Secret values must not appear in
health responses, logs, evidence records, or graph properties.

## Validation
- collection and projection lifecycle integration tests
- projection failure preserves the prior active snapshot
- graph rebuild produces equivalent results for the same snapshot and projection version
- queries reject missing, mixed, or non-ready snapshot versions

## Revisit conditions
Revisit if measured projection latency prevents required workflows, dataset scale makes full
projections impractical, or a transactional graph persistence design demonstrates materially
better correctness without unacceptable operational complexity.
