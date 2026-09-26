# Milestones and Exit Criteria

## M0 — Repository Ready
Target: Week 2

Status: complete as of 2026-09-09. The repository, CI, local Compose stack, authenticated
dependency health checks, first migration, accepted persistence ADR, documented setup, and
validated public Markdown links satisfy the M0 exit criteria.

Deliverables:
- docs baseline
- architecture skeleton
- CI
- dev environment
- issue templates
- PR template
- first ADRs

Exit:
- clean clone can run baseline services
- tests execute
- documentation links work

## M1 — AWS Identity Inventory
Target: End Month 2
Release: v0.1

Status: in progress. The first AWS-role vertical slice is complete: collection, normalization,
authoritative evidence persistence, verified Neo4j node projection, authenticated API
inspection/triggering, lifecycle visibility, and a minimal dashboard are implemented. Broader
AWS users, groups, policies, trust relationships, and OIDC coverage remain before M1 exit.

[IAM user inventory](AWS_USER_INVENTORY.md) now includes collection, normalization, persistence,
authenticated snapshot reads, and dashboard browsing. Mixed role/user graph projection remains
pending. User history has its own comparison scope; user observations do not replace the active
role snapshot.

Deliverables:
- AWS collector
- normalized identity model
- graph import
- identity dashboard

Exit:
- inventory controlled AWS account
- collection errors visible
- provider evidence retained

### M1a — Evidence-backed inventory history

Status: implemented on 2026-09-24 as a supporting milestone; broader M1 remains in progress.

Deliverables and exit criteria:
- compare two complete, ready AWS role snapshots from the same account
- deterministic added, removed, changed, and unchanged results with safe evidence references
- authenticated paginated API and usable dashboard comparison controls
- reject partial, unready, incompatible, missing, and inconsistent evidence
- preserve active inventory and exclude raw policy/tag values from responses
- deterministic unit/API tests and real PostgreSQL regression tests

See [Inventory History](INVENTORY_HISTORY.md) for implementation, limits, and follow-up scope.

### M1b — IAM user inventory history

Status: implemented on 2026-09-25 as a supporting milestone; broader M1 remains in progress.

Deliverables and exit criteria:
- compare complete retained user observations in the same account and partition
- distinguish renames from recreation using immutable user identity
- expose safe before/after references, whole-comparison counts, and cursor pagination
- reject incomplete, incompatible, missing, or corrupt observations
- provide independent role/user dashboard history controls with stale-response protection
- preserve the active role graph and existing collection/authentication contracts
- deterministic API/unit tests and real PostgreSQL regression tests

See [IAM user inventory history](USER_INVENTORY_HISTORY.md) for the plan, contract, and limits.

## M2 — AWS Attack Paths
Target: End Month 4
Release: v0.2

Deliverables:
- attack-path engine
- findings
- severity
- graph visualization
- lab scenarios

Exit:
- known lab paths found
- false-positive near-miss fixtures pass
- findings explain every path edge

## M3 — Workload Identity
Target: End Month 6
Release: v0.3

Deliverables:
- Kubernetes RBAC collection
- workload graph
- EKS/cloud identity mapping
- Kubernetes labs

Exit:
- trace workload identity to AWS resource
- RBAC escalation path demonstrated

## M4 — Agent Identity
Target: End Month 8
Release: v0.4

Deliverables:
- agent registry
- ownership
- tool inventory
- delegation model
- agent graph

Exit:
- human -> agent -> tool -> cloud path visible
- delegation represented explicitly

## M5 — Runtime Control
Target: End Month 10
Release: v0.5

Deliverables:
- gateway
- OPA integration
- ALLOW/DENY/REQUIRE_APPROVAL
- audit events
- initial SDK/example

Exit:
- sensitive demo action blocked
- decision is explainable
- policy version captured

## M6 — Agent Attack Labs
Target: End Month 11
Release: v0.6

Deliverables:
- prompt-injection scenario
- confused deputy
- delegation amplification
- malicious tool behavior
- security regression suite

Exit:
- expected attacks detected/prevented
- repeatable results

## M7 — V1
Target: End Month 12
Release: v1.0

Deliverables:
- hardened deployment
- benchmarks
- threat model
- demo
- docs
- release notes
- security review

Exit:
- flagship scenario passes end to end
- no known critical unresolved defects
- stable setup
- major claims backed by tests/benchmarks
