# Data Model

## Objective
Create a normalized model expressive enough to represent human, workload, cloud, and AI-agent identity without overfitting to one provider.

## Core entities

### Principal
An actor capable of receiving or exercising authority.

Suggested fields:
- id
- external_id
- provider
- principal_type
- display_name
- status
- created_at
- discovered_at
- last_seen
- metadata

Possible principal types:
- human
- cloud_user
- cloud_role
- service_account
- workload
- service
- ci_identity
- ai_agent
- external
- unknown

### Resource
A protected or security-relevant object.

Suggested fields:
- id
- external_id
- provider
- resource_type
- name
- criticality
- environment
- owner
- metadata

### Credential
Represents a credential relationship, not necessarily secret material.

Suggested fields:
- id
- credential_type
- principal_id
- issuer
- created_at
- expires_at
- last_used
- metadata

Do not store credential secret material unless a controlled lab explicitly requires synthetic secrets.

### Permission
Represents an action/resource authorization statement.

Suggested fields:
- id
- effect
- actions
- resources
- conditions
- source_policy_id
- provider_semantics

### Policy
- id
- provider
- name
- version
- raw_document or reference
- normalized representation
- source
- checksum

### Agent
An AI agent should be represented as a principal plus agent-specific metadata:
- framework/runtime
- purpose
- owners
- tools
- model/runtime metadata
- deployment identity
- allowed scopes
- risk tier

### Tool
Represents an external action capability available to an agent.
Fields may include:
- tool name
- server/provider
- actions
- resource domains
- sensitivity
- authentication mode

### Delegation
Represents authority delegated from one principal to another.

Potential fields:
- delegator
- delegate
- scope
- resources
- purpose
- issued_at
- expires_at
- parent_delegation
- constraints
- provenance

## Relationship types
Potential graph relationships include:

```text
OWNS
OPERATES
MEMBER_OF
ASSIGNED
ASSUMES
CAN_ASSUME
CAN_PASS_ROLE
TRUSTS
IMPERSONATES
USES_CREDENTIAL
BOUND_TO
RUNS_AS
DEPLOYED_AS
CAN_ACCESS
CAN_CALL
HOSTS_TOOL
DELEGATES_TO
ACTS_FOR
FEDERATES_WITH
HAS_POLICY
GRANTS
REACHES
DERIVED_ACCESS
```

The graph should avoid using overly generic `CAN_ACCESS` when a more precise edge exists.

## Provenance
Every important fact should support:
- source system
- source object ID
- collection timestamp
- snapshot ID
- collector version
- raw evidence reference where practical

## Fact versus inference
IdentityMesh should distinguish:

### Observed facts
Example:
"AWS role trust policy names principal X."

### Derived facts
Example:
"Principal X can assume role Y."

### Security inference
Example:
"Principal X can reach production secret Z through a risky chain."

These should not be indistinguishable.

## Temporal model
V1 may use snapshots rather than a fully temporal graph.

At minimum support:
- current snapshot
- collected_at
- first_seen
- last_seen where practical

Future versions may model historical changes and time-based attack paths.

## Schema evolution
- avoid exposing database schema directly as public API
- use migration tooling
- maintain backward compatibility for documented APIs where practical
- document breaking model changes
- create ADRs for foundational schema changes

## Open design space
Coding agents may propose:
- Pydantic model hierarchy
- SQL schema
- Neo4j labels
- edge metadata
- snapshot representation
- event envelope
- graph projection strategy

The model should be validated against real AWS, Kubernetes, and agent examples before being considered stable.
