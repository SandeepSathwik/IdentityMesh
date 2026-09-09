# Initial Backlog

This is a seed backlog, not a commitment to exact implementation order.

Legend: `[x]` implemented, `[~]` partially implemented, `[ ]` not yet implemented. Completion
here describes repository capability, not a release commitment.

## Epic A — Repository and Platform Foundation
- [x] initialize Python project
- [x] create local Docker environment
- [x] create API skeleton
- [ ] create dashboard skeleton
- [x] connect PostgreSQL
- [x] connect Neo4j
- [x] add migrations
- [x] add health endpoints
- [~] add structured logging
- [x] add CI
- [ ] add security scanning
- [x] add configuration validation

## Epic B — Domain Model
- [ ] define principal model
- [ ] define resource model
- [ ] define policy model
- [ ] define credential metadata
- [~] define provenance model
- [ ] define graph relationship vocabulary
- [x] define snapshot lifecycle model
- [ ] define event envelope

## Epic C — AWS Collector
- [~] AWS connection configuration
- [x] STS identity verification
- [ ] list users
- [ ] list groups
- [x] list roles
- [ ] managed policies
- [ ] inline policies
- [~] trust policies (raw role trust-policy evidence only)
- [ ] OIDC providers
- [x] pagination
- [x] rate-limit handling
- [x] partial permission reporting
- [x] synthetic test fixtures

## Epic D — Graph
- node persistence
- edge persistence
- provenance
- snapshot import
- graph query service
- graph API
- graph visualization

## Epic E — AWS Attack Paths
- AssumeRole
- wildcard trust
- PassRole
- admin reachability
- Secrets Manager access
- cross-account trust
- path explanation
- deduplication
- severity
- remediation

## Epic F — Kubernetes
- cluster connection
- service accounts
- roles
- cluster roles
- bindings
- workload/service-account mapping
- cloud identity mapping
- RBAC findings

## Epic G — Agent Identity
- agent registry
- ownership
- purpose
- tools
- agent framework adapter interface
- MCP-like tool inventory
- agent deployment identity
- graph relationships

## Epic H — Delegation
- delegation schema
- parent chain
- scope
- resource constraints
- expiration
- chain validation
- amplification detection

## Epic I — Runtime Gateway
- request schema
- caller authentication
- policy evaluation
- decision response
- reason codes
- fail-safe behavior
- approval placeholder
- audit

## Epic J — Policy
- OPA integration
- bundle structure
- versioning
- test harness
- agent policies
- environment policies
- delegation ceiling policy
- high-risk approval policy

## Epic K — Telemetry
- event schema
- OpenTelemetry instrumentation
- local event viewer
- Splunk mapping
- example detections
- audit query API

## Epic L — Labs
- AWS AssumeRole
- PassRole
- EKS identity
- RBAC escalation
- agent excessive scope
- delegation amplification
- indirect prompt injection
- confused deputy

## Epic M — V1 Hardening
- performance baseline
- dependency review
- threat model review
- secrets audit
- permission audit
- documentation audit
- install test
- demo script
- release automation
