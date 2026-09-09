# Architecture

## Architecture goals
IdentityMesh should be modular enough that discovery, graph analysis, policy evaluation, runtime enforcement, and telemetry can evolve independently.

The architecture should favor:
- clear trust boundaries
- explainable data flow
- deterministic security decisions
- provider isolation
- reproducible testing
- incremental deployability
- replacement of components without rewriting the whole platform

## Logical architecture

```text
                           +----------------------+
                           |      Dashboard       |
                           +----------+-----------+
                                      |
                                      v
+-------------+             +---------+----------+
|  Collectors |-----------> |      API Layer     |
+------+------+             +----+-----------+---+
       |                         |           |
       v                         v           v
+------+------+          +-------+--+   +----+---------+
| Normalizer  |---------> | PostgreSQL|   |   Neo4j      |
+------+------+          +----------+   +------+--------+
       |                                          |
       |                                          v
       |                                  +-------+--------+
       |                                  | Attack Path    |
       |                                  | / Graph Engine |
       |                                  +-------+--------+
       |                                          |
       |                                          v
       |                                  +-------+--------+
       |                                  | Risk / Finding |
       |                                  | Engine         |
       |                                  +----------------+
       |
       |          runtime
       v
+------+----------------+
| Authorization Gateway |
+------+----------------+
       |
       v
+------+----------------+
| Policy Evaluation     |
| OPA/Rego initially    |
+------+----------------+
       |
       v
ALLOW / DENY / REQUIRE_APPROVAL
       |
       v
+------+----------------+
| Event / Audit Pipeline|
+------+----------------+
       |
       +------> OpenTelemetry
       +------> Splunk
       +------> Local event store
```

## Major bounded contexts

### Collector subsystem
Responsible for retrieving source-of-truth data.

Collectors should not perform complex security conclusions. Their job is factual ingestion plus minimal provider parsing.

### Normalization subsystem
Maps provider-specific objects into IdentityMesh domain entities.

Normalization should retain enough source metadata to reconstruct why a fact exists.

The first implemented normalizer maps validated AWS IAM role evidence into the versioned
`identitymesh.principal/v1` contract. It creates a deterministic principal identity from the
AWS account and immutable role ID, records observed provenance, and explicitly defers
provider fields that belong in later policy or relationship models. It makes no effective
permission or role-assumption inference.

### Identity graph subsystem
Maintains graph representation and relationship semantics.

### Attack-path subsystem
Applies rules and graph traversal to identify dangerous transitive relationships.

### Risk subsystem
Maps findings into deterministic severity and prioritization.

### Authorization subsystem
Evaluates runtime access requests and delegation constraints.

### Gateway subsystem
Integrates authorization into tool calls or protected actions.

### Telemetry subsystem
Emits security events and audit records.

### Dashboard
Explores identities, evidence, paths, policies, findings, and events.

## Data ownership
The persistence boundary is defined by
[ADR-0001](adr/0001-persistence-and-snapshot-projection.md): PostgreSQL is authoritative for
operational state and collected evidence; Neo4j contains versioned, rebuildable graph
projections. They are not co-equal sources of truth.

### PostgreSQL
Good fit for:
- configuration
- policies metadata
- users
- agent registry
- event indexes
- approvals
- findings metadata
- jobs/collection state
- snapshots

### Neo4j
Good fit for:
- principals
- resources
- permission edges
- delegation
- trust
- attack paths
- graph projections

Graph data must be keyed by snapshot and projection version. Readers must not combine facts
from different snapshots or expose a projection before its snapshot is ready.

### Redis
Optional for:
- short-lived cache
- job coordination
- policy/result cache
- rate limiting

Redis is not mandatory if it creates complexity without measurable benefit.

## Snapshot lifecycle

The implemented lifecycle is:

```text
collecting -> collected -> projecting -> ready
     |            |             |
     +------------+-------------+-> failed
```

PostgreSQL serializes transitions and owns a singleton pointer to the active ready snapshot.
Completing a projection and evaluating active promotion occur in one transaction. Sequence
ordering prevents an older collection that finishes late from replacing a newer ready
snapshot. A failed collection or projection never displaces the previous active snapshot.

The graph projection itself, projection verification, retained evidence tables, and retention
policy are not yet implemented.

## Service topology

### Early stage
Prefer a modular monolith or small number of services.

Suggested:
- API service
- worker/collector process
- runtime gateway
- dashboard
- data services

Avoid premature microservices.

### Later stage
Split components only when:
- scaling characteristics differ materially
- fault isolation is needed
- security boundaries benefit
- deployment independence is valuable
- team/project complexity justifies it

## Trust boundaries

### External provider boundary
AWS/Kubernetes/agent ecosystems are untrusted inputs.

### Collector boundary
Collected metadata may be incomplete or stale.

### Policy boundary
Policies are privileged configuration.

### Runtime request boundary
Action requests may be malicious or manipulated.

### Dashboard/API boundary
User input and query parameters are untrusted.

### AI boundary
LLM-generated analysis is advisory unless converted into deterministic validated data.

## Security invariants

1. A runtime decision must be attributable to a policy/rule version.
2. A finding must be attributable to source facts and analysis logic.
3. No security-critical decision may depend solely on free-form LLM output.
4. Delegated authority must not silently exceed upstream authority.
5. Secret values must not be emitted in logs.
6. Collector credentials must use minimum practical privilege.
7. Dangerous lab infrastructure must be clearly isolated and tear-down capable.
8. Authentication failure at the runtime gateway must not default to allow.

## Availability model
V1 is not an HA product. Prioritize correctness and reproducibility.

For runtime enforcement:
- failure mode must be explicit
- sensitive actions should default to fail-closed unless policy explicitly chooses otherwise
- availability tradeoffs should be configurable and documented

## Extension points
Architecture should allow future:
- cloud collectors
- agent framework adapters
- policy engines
- graph rules
- telemetry sinks
- approval providers
- resource enrichers

## Open architectural questions
These are intentionally not frozen:
- REST-only versus selected event-driven flows
- task queue implementation
- policy bundle distribution
- graph schema details
- approval orchestration
- exact deployment topology
- SDK design
- persistence strategy for large event volumes
- whether gateway is reverse proxy, library, sidecar, or supports several modes

Material decisions should be captured as ADRs.
