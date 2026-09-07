# Testing Strategy

## Objective
Security software is only credible when its claims are reproducible.

IdentityMesh will use layered testing.

## Test pyramid

### Unit tests
Cover:
- parsers
- normalization
- graph edge generation
- policy helpers
- risk scoring
- request validation
- reason-code generation

Target:
- general codebase: >85% where meaningful
- critical authorization logic: >95%
- critical deterministic policy rules: complete scenario coverage

Coverage percentage is a signal, not the goal.

### Contract tests
Validate boundaries:
- AWS collector output
- Kubernetes collector output
- policy input/output
- graph persistence
- event schema
- API response schemas

### Integration tests
Examples:
- API + PostgreSQL
- analysis + Neo4j
- gateway + policy engine
- event pipeline + test sink
- collector + mocked provider

### End-to-end tests
Reference scenarios:
- discovery -> graph -> finding
- agent request -> policy -> denial -> event
- approval -> constrained allow
- lab deployment -> collection -> expected finding

### Security tests
- auth bypass attempts
- malformed delegation
- expired delegation
- policy injection
- unsafe graph queries
- SSRF defenses
- secret leakage
- privilege escalation regression
- prompt-injection-triggered tool request
- fail-closed behavior

### Property/invariant tests
Useful for:
- delegation never widening silently
- denied policy always denying
- graph traversal depth bounds
- equivalent normalized policies producing stable results

### Performance tests
Measure:
- collector throughput
- graph ingest rate
- attack-path runtime
- gateway decision latency
- dashboard query latency
- memory usage

Do not optimize before measuring.

## Test fixtures
Use:
- synthetic provider responses
- anonymized examples
- intentionally vulnerable lab data
- provider-specific edge cases

No real secrets.

## Golden scenarios
Maintain a small set of canonical end-to-end scenarios whose expected output is versioned.

Example:
`golden/aws_passrole_to_secret`

Expected:
- entities
- relationships
- path
- severity
- explanation
- remediation

## CI requirements
Every PR should run:
- formatting
- linting
- type checking
- unit tests
- fast integration tests
- dependency/security checks

Security-critical PRs should additionally run:
- policy tests
- attack-path regression tests
- gateway security tests

## Flaky tests
Do not normalize flaky CI.
A flaky test should be:
- fixed
- isolated with a tracked issue
- or removed if invalid

## Test naming
Tests should describe behavior.

Prefer:
`test_delegation_cannot_exceed_parent_scope`

Avoid:
`test_case_17`

## AI-generated code
AI-generated implementation must not receive reduced testing standards.

The coding agent should:
- write tests with the feature
- explain edge cases
- identify untested behavior
- avoid tests that merely mirror implementation

## Manual validation
Human validation remains required for:
- cloud IAM behavior
- Kubernetes security semantics
- representative agent flows
- sensitive authorization changes
- public benchmark claims
