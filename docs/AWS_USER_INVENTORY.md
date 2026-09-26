# AWS IAM user collection

## Delivery boundary

IAM user inventory now supports read-only collection, stable normalization, transactional
PostgreSQL persistence, authenticated snapshot-specific reads, and a dashboard panel. It is
tested with synthetic provider responses, the real Boto3 paginator under Botocore Stubber,
and isolated PostgreSQL integration tests. M1 remains in progress.

User observations are separate from the active role graph. Complete user collections remain
`collected`; incomplete collections become `failed` with retained evidence and reason codes.
They never replace the active role snapshot, enter role comparisons, or become graph nodes.
Mixed inventory promotion and user comparison remain future work.

The goal is to establish reliable user-listing evidence before expanding the active graph.
Inputs are an explicit allowed account ID, a snapshot UUID, and an AWS provider adapter.
The output is an `AwsUserCollection` with provenance, validated users, and safe collection gaps.

## Evidence contract

- `aws.iam.user/v1`: immutable AWS user ID, ARN, name, path, creation time, optional
  password-last-used time, account, snapshot, collector identity, timestamp, and version.
- `aws.iam.user.collection/v1`: a complete, partial, or failed listing attempt.
- Collector version: `aws-iam-user/0.1`.
- `uncollected_fields` explicitly identifies tags and permissions boundaries. These are
  outside the listing contract, not known-empty values.

AWS documents that [ListUsers](https://docs.aws.amazon.com/IAM/latest/APIReference/API_ListUsers.html)
omits tags and permissions boundaries. The optional password-last-used value does not prove
whether a password currently exists; see the
[User contract](https://docs.aws.amazon.com/IAM/latest/APIReference/API_User.html).
No credentials, policies, memberships, human ownership, or effective permissions are derived.
Only selected listing attributes enter the evidence; unknown provider fields are discarded.

## Completeness and failure behavior

STS caller identity must match the required account allowlist before listing starts.
User ARNs must match their account, partition, path, and name. Timestamps require timezones.
Duplicate ARNs or immutable user IDs are collection gaps, including duplicates across pages.
The first validated observation is retained, but the attempt cannot be complete.

A complete attempt requires a terminal page with `IsTruncated=false` and no gaps. An explicit
empty terminal page can establish an empty listing. Zero pages, missing continuation markers,
repeated markers, malformed pagination, and iterator exhaustion before a terminal page cannot.
Empty intermediate pages are followed normally. Pagination is limited to 1,000 accepted pages
and evidence to 10,000 users; exceeding either produces `AWS_COLLECTION_LIMIT_EXCEEDED`.
The iterator may fetch one additional page to detect the page limit.

An incomplete attempt with retained valid users is partial. An attempt with gaps and no valid
users is failed. Provider exception messages and endpoint details never enter gap messages.
The existing AWS error classifications and bounded SDK retry/timeout configuration are reused.
No attempt in this increment can promote or replace the active role snapshot.

These are listing observations, not an atomic account-wide view: IAM can change during
pagination. A valid list does not establish complete access or credential coverage. Live AWS
behavior remains subject to owner-run validation in the controlled account.

## Required read permission

User collection requires one additional action beyond the role collector's permissions:

```json
{
  "Effect": "Allow",
  "Action": "iam:ListUsers",
  "Resource": "*"
}
```

This is a deployment requirement, not an automatically applied policy. Account-wide discovery needs
the listing action; it has no resource-level ARN scope. The existing STS identity check and
configured account allowlist remain required. AWS's
[IAM permissions example](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_examples_iam-add-tag.html)
uses `Resource: "*"` for listing users.

`GetUser`, tagging, group membership, access-key, credential-report, and policy APIs are not
requested. A broader account-authorization export was deferred because this increment only
needs user identities. No IAM policy, trust relationship, or deployed permission is changed.
Review this permission delta before live collection; live validation is owner-run. The route
only contacts AWS when explicitly triggered, using the standard credential chain.

## Storage, identity, and API

Migration `20260925_0003` adds user attempt/gap tables and reuses the existing provider evidence
and principal tables. Apply `alembic --config pyproject.toml upgrade head` before starting the
updated API. It does not rewrite role data. Downgrade refuses to remove the tables when user
attempts are retained, preventing orphaned evidence or silent data loss.

The normalized `cloud_user` UUID includes AWS partition, account, object type, and immutable
user ID. Renaming preserves identity; recreation produces a new identity. No human ownership
or current credential status is inferred. Role UUID derivation remains unchanged.

Persistence locks the snapshot row and atomically writes the attempt, gaps, evidence,
principals, and lifecycle outcome. Identical concurrent retries are idempotent; conflicting
retries, wrong collector versions, and non-collecting writes fail. User and role collection
routes share the existing PostgreSQL advisory lock. Provider work runs outside the event loop.

Both endpoints require the existing bearer token:

- `POST /api/v1/collections/aws/iam/users` returns `identitymesh.user-collection-run/v1`,
  including snapshot ID, counts, completeness, lifecycle status, and `activated: false`.
- `GET /api/v1/snapshots/{snapshot_id}/users?limit=50&cursor=<UUID>` returns
  `identitymesh.user-inventory-page/v1`, safe principal references, account, observation time,
  collection gaps, and explicit uncollected fields. Limit is 1–100. Omit cursor initially;
  reuse the same snapshot ID with `next_cursor` for later pages.

The read path checks evidence, normalized records, counts, and lifecycle in one read-only
repeatable-read transaction with a five-second statement timeout. It validates at most 10,000
users before returning a UUID-ordered page. Password-last-used remains in evidence and is
excluded from API principal references. Empty incomplete results never assert absence.

Missing snapshots return 404. Wrong scope and unfinished snapshots return 409. Missing or
inconsistent retained evidence returns 503 with `USER_INVENTORY_SOURCE_INVALID`; dependency
failures use `USER_INVENTORY_UNAVAILABLE`. Unexpected collection failures retain a failed
snapshot and return a safe error without provider details.

In the dashboard, **Collect users** starts a run and selects its observation. The selector
lists user attempts among the latest 100 snapshots, including failures. Pagination and changed
selections retain the explicit snapshot identity, and stale responses cannot overwrite a new
selection. This panel is independent of the active role graph and role comparison selectors.

## Validation and follow-up

Run the deterministic collector checks without AWS credentials:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_aws_iam_user_collector.py tests/test_aws_iam_collector.py
```

Tests cover pagination, explicit empty results, allowlist rejection, malformed identity and
records, duplicate identities, bounded collection, safe provider failures, consistent evidence
envelopes, and SDK request parameters. PostgreSQL tests cover atomic finalization, concurrent
retries, conflicts, rollback, corrupt evidence, HTTP collection/reads, pagination, shared locks,
active-role preservation, comparison scope rejection, and migration upgrade/downgrade safety.
No new dependencies are needed.

Subsequent increments must define reviewed snapshot scope before user graph integration and
mixed inventory promotion. Role-only snapshots must never be
compared to user or mixed inventories as though their absence semantics were equivalent.
