# IAM user inventory history

## Milestone and acceptance plan

M1b extends retained IAM user observations with evidence-backed history in the API and
dashboard. Broader M1 AWS coverage remains in progress.

1. Read two explicit user snapshots from PostgreSQL in one read-only repeatable-read
   transaction. Reuse user inventory validation for lifecycle, supported collector version,
   evidence counts, normalized principals, and collection envelopes.
2. Require complete observations from the same account and AWS partition. Reject partial,
   failed, unfinished, mixed-scope, missing, or inconsistent sources before reporting absence.
3. Compare stable identities and selected listing attributes deterministically. Return counts,
   safe before/after references, and UUID cursor pagination.
4. Add independently scoped dashboard controls for role and user history, including rename
   display, pagination, error clearing, and stale-response protection.
5. Verify identity recreation, complete-empty observations, ordering, malformed requests,
   dependency failure, retained-data corruption, and preservation of the active role snapshot.

These steps are implemented. No database migration, dependency, cloud permission, graph
promotion rule, authentication change, or retention change is required.

## Approach and alternatives

The service reuses validated PostgreSQL user reads, then compares the two collections in
memory. Both inputs are read in the same transaction with a five-second SQL statement timeout.
Each collection is bounded to 10,000 users. Each page revalidates both sources.

User observations remain `collected`; they do not need a role-only graph projection to support
history. The existing role comparison endpoint still requires ready role snapshots and is
unchanged. A shared dashboard controller manages independent state for each panel.

Mixed user/role graph promotion was deferred because it needs an explicit scope design before
it can preserve active-inventory completeness. A persisted change-event stream would add
storage and retention complexity without improving this bounded read-only use case. This
increment follows the evidence-first approach of
[ADR-0002](adr/0002-observed-inventory-comparison.md), with a separate user contract.

## Meaning of a change

- Identity uses the existing UUID derived from partition, account, object type, and immutable
  AWS user ID. Rename preserves identity. Recreation under the same ARN is removed plus added.
- Compared fields are `user_name`, `arn`, `path`, and `created_at`. A rename or move may change
  several of these fields together.
- Collection time, collector session, and password-last-used are excluded from change detection.
  Tags and permissions boundaries are uncollected and cannot establish changes.
- A removal means absence from the later complete listing, not proof of a deletion event.
  AWS listing is not atomic. Creation sequence orders the observations, not AWS transaction time.
- Comparing a snapshot with itself is valid. Base sequence must not exceed target sequence.
  Both collection times remain visible; there is no automatic freshness threshold.
- Results describe metadata observations. They do not infer ownership, credential status,
  effective access, risk, or authorization decisions.

Before/after references contain snapshot ID, principal UUID, immutable user ID, display name,
source ARN, and collection time. Responses include changed field names, not raw evidence or
password usage. Account and partition remain explicit even for complete-empty observations.

## HTTP contract

`GET /api/v1/snapshots/users/compare` requires the existing bearer token.

| Parameter | Meaning |
|---|---|
| `base_snapshot_id` | Required UUID of the earlier complete user observation |
| `target_snapshot_id` | Required UUID of the later complete user observation |
| `limit` | Page size 1–100, default 50 |
| `cursor` | Optional last returned principal UUID from this same pair |

The `identitymesh.user-comparison/v1` response pins both snapshot IDs, account, partition,
collection times, compared fields, whole-comparison added/removed/changed/unchanged counts,
`total_count` of changes, UUID-ordered `items`, and `next_cursor`. Counts are independent of
page size. Keep both IDs unchanged when requesting subsequent pages. An empty page does not
imply zero total changes.

| HTTP | Reason code | Meaning |
|---|---|---|
| 401 | `AUTHENTICATION_FAILED` | Missing or invalid bearer token |
| 404 | `SNAPSHOT_NOT_FOUND` | An input snapshot does not exist |
| 409 | `COMPARISON_SCOPE_MISMATCH` | Wrong collector, account, or partition |
| 409 | `COMPARISON_NOT_READY` | Input has an unsupported lifecycle state |
| 409 | `COMPARISON_INCOMPLETE` | Valid retained collection is partial or failed |
| 409 | `COMPARISON_ORDER_INVALID` | Base sequence is newer than target |
| 422 | `REQUEST_VALIDATION_FAILED` | Malformed UUID, cursor, or page limit |
| 503 | `COMPARISON_SOURCE_INVALID` | Missing, corrupt, oversized, or inconsistent evidence |
| 503 | `COMPARISON_UNAVAILABLE` | Missing service, database failure, or timeout |

## Dashboard and operation

Connect with the configured token, then choose base and target under **Compare user
observations**. The selectors offer collected user snapshots among the latest 100 attempts.
The server validates completeness; selector eligibility alone is not proof of valid evidence.
Role choices remain restricted to ready role snapshots. **Load more changes** retains the
selected pair; changing a selection clears results and ignores older outstanding responses.
A page failure clears the result list to avoid displaying a successful-looking partial result.

The API supports any retained pair by UUID, including observations older than dashboard
choices. Reads do not query Neo4j, contact AWS, promote snapshots, or modify retained data.
Normal service startup still requires the existing database configuration.

## Validation and limitations

`tests/test_user_comparison.py` covers deterministic semantics, source compatibility, safe
references, API validation/authentication, and real PostgreSQL history and corruption cases.
Existing role comparison and graph tests remain required regression checks. All AWS data in
these tests is synthetic; live provider behavior is not claimed.

Reads cost O(n log n) ordering and O(n) memory within the collection bound. SQL timeout is per
statement, not an end-to-end request deadline. Database cross-record checks detect inconsistency
but cannot protect against a privileged database actor coherently rewriting all evidence.
Saved comparisons, older-history dashboard browsing, mixed inventory projection, and broader
AWS identity coverage remain future work. This supporting milestone does not create a release tag.
