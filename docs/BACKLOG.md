# Initial Backlog

This is a seed backlog, not a commitment to exact implementation order.

## Epic A — Repository and Platform Foundation
- initialize Python project
- create local Docker environment
- create API skeleton
- create dashboard skeleton
- connect PostgreSQL
- connect Neo4j
- add migrations
- add health endpoints
- add structured logging
- add CI
- add security scanning
- add configuration validation

## Epic B — Domain Model
- define principal model
- define resource model
- define policy model
- define credential metadata
- define provenance model
- define graph relationship vocabulary
- define snapshot model
- define event envelope

## Epic C — AWS Collector
- AWS connection configuration
- STS identity verification
- list users
- list groups
- list roles
- managed policies
- inline policies
- trust policies
- OIDC providers
- pagination
- rate-limit handling
- partial permission reporting
- mocked test fixtures

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
