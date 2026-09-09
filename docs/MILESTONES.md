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

Status: in progress. AWS IAM role collection and role-to-principal normalization are complete.
Persistence, graph import, API inspection, dashboard rendering, and broader AWS identity
coverage remain.

Deliverables:
- AWS collector
- normalized identity model
- graph import
- identity dashboard

Exit:
- inventory controlled AWS account
- collection errors visible
- provider evidence retained

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
