# Integration Contracts

## Purpose
Define conceptual contracts between major subsystems without over-prescribing implementation.

## Collector -> Normalizer
Collector output must include:
- provider
- object type
- source identifier
- collection timestamp
- raw or structured evidence
- collection status

Normalizer must:
- validate
- produce internal IDs
- preserve source IDs
- preserve provenance
- report unsupported fields explicitly

## Normalizer -> Graph
Graph input should contain:
- nodes
- relationships
- source snapshot
- fact/inference classification
- evidence reference

Graph import should be idempotent for a snapshot.

## Graph -> Attack Path Engine
The engine needs:
- typed nodes
- typed relationships
- criticality
- evidence
- snapshot/version
- bounded traversal

The engine returns findings rather than mutating source facts.

## Attack Path -> Finding
Finding contract includes:
- rule ID
- source
- target
- ordered path
- severity
- evidence
- explanation
- remediation
- analysis version

## Runtime Gateway -> Policy
Input:
- authenticated principal
- acting agent/workload
- action
- resource
- delegation context
- request context

Output:
- decision
- reason code
- policy version
- optional constraints
- explanation metadata

## Policy -> Audit
Every decision should create an event even if a downstream system fails.

## Approval
Approval should reference:
- original request
- policy decision
- approver
- time
- scope
- expiration
- final decision

## Event export
Export failure must not rewrite the authorization outcome.

Retry may occur independently.

## Versioning
Contracts should support explicit schema versions where cross-service compatibility matters.

## Open implementation freedom
These contracts may be:
- Python protocols/interfaces
- Pydantic models
- HTTP schemas
- events
- database records

Choose based on deployment boundaries, not preference.
