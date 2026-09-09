# Roadmap

## Philosophy
The roadmap is directional. Milestones define outcomes, not rigid implementation.

The team may reorder internal tasks when:
- dependencies require it
- experiments invalidate assumptions
- a safer/simpler design appears
- provider behavior changes
- testability improves

Major scope changes should be documented.

## Current position

Phase 0 is substantially complete: the repository, local service stack, CI baseline,
configuration validation, health checks, persistence decision, migrations, and snapshot
lifecycle are in place. The first Phase 1 increment collects AWS IAM roles, but it is not yet
connected to normalization, persistence, graph projection, the API, or a dashboard.

This status note does not change the phase outcomes or expand V1 scope.

---

## Phase 0 — Foundation
### Weeks 1–2

Outcomes:
- repository initialized
- product charter accepted
- threat model baseline
- architecture baseline
- local development skeleton
- issue/PR process
- coding standards
- test strategy
- CI baseline
- first ADRs

Exit criteria:
- new contributor/agent understands the project
- local skeleton runs
- CI runs
- no cloud credentials required for basic development

---

## Phase 1 — IdentityMesh Core
### Months 1–2
Target release: `v0.1`

Outcomes:
- FastAPI service
- PostgreSQL
- Neo4j
- local Docker environment
- authentication baseline
- AWS IAM collector
- normalized identity model
- basic dashboard
- collection snapshots

AWS target:
- users
- groups
- roles
- policies
- trust policies
- OIDC providers where practical

Exit criteria:
- connect controlled AWS test account
- inventory identities
- inspect normalized records
- inspect basic graph

---

## Phase 2 — Attack Paths
### Months 3–4
Target release: `v0.2`

Outcomes:
- graph relationship model
- effective privilege logic for selected AWS cases
- path engine
- findings model
- risk baseline
- remediation explanations
- graph visualization

Initial paths:
- AssumeRole
- cross-account trust
- broad admin reach
- PassRole-like escalation
- secrets reachability

Exit criteria:
- lab contains known dangerous paths
- IdentityMesh detects expected findings
- results are reproducible

---

## Phase 3 — Kubernetes and Workload Identity
### Months 5–6
Target release: `v0.3`

Outcomes:
- Kubernetes collector
- RBAC model
- service account/workload graph
- cloud workload identity join
- Kubernetes attack-path rules
- lab scenarios

Exit criteria:
- trace workload -> service account -> cloud role -> resource
- identify at least one RBAC escalation scenario
- explain cross-domain path

---

## Phase 4 — AI Agent Identity
### Months 7–8
Target release: `v0.4`

Outcomes:
- agent registry
- agent ownership
- purpose/scope
- tool inventory
- MCP-like adapters
- agent-to-cloud graph relationships
- delegated context model

Exit criteria:
- register/discover agent
- display tool relationships
- trace agent -> tool -> cloud resource
- model human -> agent delegation

---

## Phase 5 — Runtime Authorization
### Months 9–10
Target release: `v0.5`

Outcomes:
- authorization gateway/API
- policy engine integration
- allow/deny/approval
- delegation ceiling
- policy versioning
- audit events
- sample SDK/integration

Exit criteria:
- protected tool call can be evaluated
- out-of-scope action denied
- high-risk action can require approval
- decisions include reason and audit event

---

## Phase 6 — Adversarial Validation
### Month 11
Target release: `v0.6`

Outcomes:
- agent security labs
- confused deputy
- delegation abuse
- indirect prompt injection -> unauthorized tool request
- credential misuse scenario
- attack regression tests
- SIEM detections

Exit criteria:
- attacks produce expected detection/prevention
- no uncontrolled targets
- results documented

---

## Phase 7 — V1 Hardening
### Month 12
Target release: `v1.0`

Focus:
- reliability
- benchmarks
- security review
- threat model update
- documentation
- demo
- migration/setup
- changelog
- reproducibility
- UX polish

Exit criteria:
- flagship scenario works end to end
- setup documented
- tests stable
- security posture documented
- public demo quality achieved

---

## Post-V1 candidates
- Azure
- GCP
- GitHub Actions/OIDC identity
- temporal attack paths
- policy recommendations
- auto-generated remediation PRs
- enterprise tenancy
- workload attestation
- SPIFFE/SPIRE
- additional agent framework adapters
- expanded SIEM integrations
