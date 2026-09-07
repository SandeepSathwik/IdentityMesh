# Implementation Strategy

## Goal
Convert the roadmap into a practical development sequence without forcing exact internal design.

## Strategy
Build **vertical slices** that prove end-to-end value early.

Avoid spending months building infrastructure with no visible security outcome.

## Slice 0 — Skeleton
Prove:
- API boots
- database connections work
- CI works
- configuration is validated
- basic health dashboard works

## Slice 1 — One AWS role end to end
Implement enough to:
1. collect one role type
2. normalize
3. store
4. graph
5. expose through API
6. render in UI

Then expand entity coverage.

## Slice 2 — One attack path
Create a controlled AWS path and detect it.

Do not build a generic graph engine before validating one useful rule.

## Slice 3 — Findings workflow
Add:
- finding persistence
- severity
- evidence
- remediation
- UI

## Slice 4 — Kubernetes join
Demonstrate:
workload -> service account -> AWS role.

## Slice 5 — Agent identity
Demonstrate:
human -> agent -> tool -> AWS role.

## Slice 6 — Runtime denial
Protect one synthetic tool action with deterministic policy.

## Slice 7 — Delegation
Demonstrate nested delegation and deny privilege amplification.

## Slice 8 — Telemetry
Trace one denied request from gateway to SIEM-compatible event.

## Slice 9 — Attack lab
Trigger an indirect-prompt-injection scenario whose dangerous tool call is blocked by policy.

## Development cadence
For each slice:
1. issue
2. threat review
3. minimal implementation
4. tests
5. demo
6. docs
7. cleanup/refactor
8. release or merge

## Architecture discipline
Do not generalize until there are at least two real use cases for the abstraction.

Do not introduce:
- message broker
- microservice
- plugin framework
- custom DSL
- distributed cache
unless a concrete requirement appears.

## Spikes
Use time-boxed experimental code for:
- graph algorithms
- policy engines
- agent protocol integration
- workload identity
- performance

Spikes do not need production polish but must record findings.

## Human checkpoints
Human review should occur at:
- first normalized model
- first graph schema
- first attack rule
- first authorization API
- first delegation model
- first production-like cloud permissions
- first public demo
- every release
