# ADR-0002: Compare complete retained inventory observations

- Status: Accepted
- Date: 2026-09-24
- Scope: Read-only AWS role inventory history within the existing local/test security model

## Context

The role pipeline retains complete and incomplete collection evidence in PostgreSQL and
publishes verified ready graph projections. Analysts need to inspect what differs between
collections without interpreting partial collection as deletion or metadata as effective access.

## Decision

Compare two explicitly selected ready snapshots from authoritative PostgreSQL. Require complete
role attempts without gaps, the same AWS account, and the supported `aws-iam-role/0.1`
collector. Use one read-only repeatable-read transaction for metadata, counts, evidence, and
normalized principals. Validate schemas, envelope provenance, row columns, and reproduction of
normalized principals before computing results.

Use existing stable principal UUIDs. Return selected metadata field names and safe role
references with whole-comparison counts and UUID cursor pagination. Preserve raw policy and
tag value exclusion. Apply a 10,000-role limit per snapshot and five-second statement timeout.
The contract and exact comparison semantics are defined in [Inventory History](../INVENTORY_HISTORY.md).

## Alternatives considered

- Compare Neo4j projections: rejected because node projections intentionally omit metadata
  needed for change detection and PostgreSQL already owns the evidence.
- Infer deletions from any collection: rejected because partial access cannot establish absence.
- Build a persisted event/change stream: deferred because immutable snapshots already support
  reproducible reads without new migrations, retention policy, or write coordination.
- Interpret policy changes as changed permissions: deferred until reviewed deterministic
  effective-access semantics exist.

## Consequences

This is additive: existing APIs, collection permissions, authentication, graph schema,
promotion rules, and retention behavior remain compatible. No migration is required; rolling
back application code removes the route without changing retained data.

Reads cost O(n log n) ordering and O(n) memory within the role limit and repeat source validation
for each page. Old snapshots describe old observations. AWS pagination is not atomic, and
syntactic policy differences can overstate semantic change. Database consistency checks do
not protect against a privileged actor coherently rewriting authoritative data. Comparison
results are observational aids, not findings or runtime decisions.
