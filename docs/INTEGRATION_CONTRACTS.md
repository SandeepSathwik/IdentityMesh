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

The first implemented contract is the AWS IAM role collector:

- role evidence schema: `aws.iam.role/v1`
- collection envelope schema: `aws.iam.role.collection/v1`
- provider operations: `sts:GetCallerIdentity` and paginated `iam:ListRoles`
- statuses: `complete`, `partial`, and `failed`
- gaps: operation, stable reason code, retryability, and a bounded safe message

`complete` includes verified caller identity and no gaps, including when the role list is
legitimately empty. `partial` includes verified caller identity, at least one valid role, and
one or more gaps. `failed` contains no roles and at least one gap. This distinction prevents
unavailable or malformed provider data from being interpreted as absence.

Current AWS gap reason codes are:

- `AWS_ACCESS_DENIED`
- `AWS_AUTHENTICATION_FAILED`
- `AWS_THROTTLED`
- `AWS_SERVICE_UNAVAILABLE`
- `AWS_CONNECTION_FAILED`
- `AWS_API_ERROR`
- `AWS_MALFORMED_RESPONSE`

The contract contains factual trust-policy evidence but makes no effective-permission,
ownership, or attack-path inference.

Normalizer must:
- validate
- produce internal IDs
- preserve source IDs
- preserve provenance
- report unsupported fields explicitly

The first implemented normalizer maps `AwsRoleEvidence` into
`identitymesh.principal/v1`. It uses the AWS account ID and immutable role ID to derive a
stable internal UUID, preserves observed source provenance, and reports evidence fields
deferred from the principal contract. Collection orchestration and persistence wiring are not
yet implemented.

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
