# Inventory History

## Objective and delivery

M1a delivers evidence-backed AWS role inventory change tracking. Analysts can compare two
retained ready snapshots through the authenticated API and dashboard. This extends the first
role vertical slice; it does not complete the broader M1 AWS inventory release.

## Plan and acceptance criteria

1. Read two explicit snapshot IDs from authoritative PostgreSQL in one repeatable-read,
   read-only transaction. Require ready snapshots, complete collection attempts, zero gaps,
   and matching account and supported collector version.
2. Check evidence/principal counts, validate stored schemas and provenance, and verify that
   normalization of each evidence record reproduces its stored principal.
3. Compare stable role identities and selected observed metadata deterministically. Return
   added, removed, changed, and unchanged counts with paginated evidence references.
4. Expose the contract under the existing bearer authentication and provide snapshot choices,
   counts, change details, and next-page navigation in the dashboard.
5. Validate complete-empty inputs, recreation, scope mismatch, corrupt/missing data, malformed
   requests, dependency failures, pagination, and preservation of the active snapshot.

These steps are implemented. No migration, new dependency, cloud permission, retention rule,
graph relationship, or authorization change is required. See
[ADR-0002](adr/0002-observed-inventory-comparison.md) for the approach and alternatives.

## Comparison semantics

The base snapshot must have a sequence ID no greater than the target's. Comparing a snapshot
with itself is valid. Sequence ordering describes collection creation order, not a guarantee
about AWS transaction time. Both collection timestamps are returned so old observations remain
visible. There is no automatic freshness threshold or claim about current live AWS state.

Role identity uses the existing UUID derived from account ID and immutable AWS role ID. A
deleted and recreated role with the same name/ARN is a removal plus an addition. `removed`
means absent from the later complete observation, not proof of a deletion event. AWS listing
is not an atomic point-in-time snapshot.

For a role present in both snapshots, v1 compares:

- role name, ARN, path, and creation time
- trust-policy document
- description, maximum session duration, permissions-boundary ARN, and tags

Dictionary key order is ignored; array order and JSON scalar types remain significant.
For example, a policy value changing from `true` to `1` is a difference. A reordered policy array
can therefore produce a metadata difference even when AWS access semantics are equivalent.
Collection timestamps, collector session ARN, and last-used metadata are excluded from change
detection. Missing optional evidence versus a populated value is a difference in observations,
not a claim that an AWS setting changed. Comparisons do not evaluate policies, establish
effective access, create findings, or assign risk scores.

Only changed field **names** are returned for metadata differences. Before/after references
contain snapshot ID, principal ID, role ID, display name, source ARN, and collection time. Raw
policies, tag values, descriptions, boundary values, and credentials are excluded.

## HTTP contract

`GET /api/v1/snapshots/compare` requires the same bearer token as other data routes.

| Parameter | Meaning |
|---|---|
| `base_snapshot_id` | Required UUID of the earlier ready snapshot |
| `target_snapshot_id` | Required UUID of the later ready snapshot |
| `limit` | Page size, 1–100; default 50 |
| `cursor` | Optional last returned principal UUID from this same snapshot pair |

The versioned `identitymesh.snapshot-comparison/v1` response pins both snapshot IDs and
collection timestamps, account ID, compared fields, whole-comparison counts, a UUID-ordered
`items` page, and `next_cursor`. Counts are independent of page size and cursor. An empty page
does not imply zero total changes. Reuse both IDs with every next-page request.

| HTTP | Reason code | Meaning |
|---|---|---|
| 401 | `AUTHENTICATION_FAILED` | Missing or invalid bearer token |
| 404 | `SNAPSHOT_NOT_FOUND` | At least one ID does not exist |
| 409 | `COMPARISON_NOT_READY` | At least one snapshot is not ready |
| 409 | `COMPARISON_SCOPE_MISMATCH` | Account or supported collector version differs |
| 409 | `COMPARISON_ORDER_INVALID` | Base sequence is later than target sequence |
| 413 | `COMPARISON_TOO_LARGE` | A snapshot contains over 10,000 roles |
| 422 | `REQUEST_VALIDATION_FAILED` | Invalid UUID, cursor, or limit |
| 503 | `COMPARISON_SOURCE_INVALID` | Incomplete, missing, or inconsistent retained evidence |
| 503 | `COMPARISON_UNAVAILABLE` | Comparison service/database is unavailable or timed out |

## Operation and limits

The dashboard offers ready snapshots from the most recent 100 attempts. The API can compare
any retained pair by ID, even when neither snapshot is active. Every page revalidates its
sources. Reads never promote a snapshot or modify stored evidence. No Neo4j query is needed
for comparison, although normal service startup/readiness still includes Neo4j.

Each snapshot is bounded to 10,000 roles and each SQL statement to five seconds. This is an
initial synchronous implementation that reads both role sets per page; it is not a benchmark
claim. PostgreSQL remains trusted authoritative storage. Cross-record checks catch missing
and inconsistent records but are not cryptographic protection against a database administrator
rewriting evidence and metadata together. Existing projection digests and persistence retry
digests retain their original purposes.

## Validation and follow-up

`tests/test_snapshot_comparison.py` covers deterministic comparison, safe references, API
authentication and validation, and real PostgreSQL persistence/corruption scenarios. Existing
full-pipeline tests continue to cover verified Neo4j promotion. All fixtures are synthetic and
require no AWS credentials.

Broader AWS users/groups/policies/OIDC inventory, reviewed trust relationships, effective-access
analysis, saved comparisons, older-history browsing in the dashboard, and larger-scale query
optimization remain follow-up work. No release tag is created for this supporting milestone.
