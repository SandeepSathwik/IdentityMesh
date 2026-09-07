# System Requirements

## Requirement language
- **MUST**: required for correctness or security
- **SHOULD**: strong default; deviation should be justified
- **MAY**: optional
- **OPEN**: intentionally left for design exploration

## Identity model requirements
- MUST assign globally unique internal IDs.
- MUST preserve original provider IDs.
- MUST record principal type.
- MUST support human, workload, cloud, service, agent, and external principal categories.
- MUST preserve source/provenance of collected facts.
- SHOULD model ownership separately from authority.
- SHOULD model credentials separately from principals.
- SHOULD support temporal metadata such as discovered_at and last_seen.
- OPEN: whether all resource types share one base model or use typed subclasses.

## Collector requirements
- MUST operate with least practical privilege.
- MUST not require administrative credentials solely for convenience.
- MUST handle pagination and rate limits.
- MUST handle partial access.
- MUST distinguish unavailable data from absent data.
- MUST support repeat collection.
- SHOULD be idempotent.
- SHOULD support snapshot identifiers.
- SHOULD surface permission gaps.
- OPEN: scheduler model and queue implementation.

## Graph requirements
- MUST distinguish direct facts from inferred edges.
- MUST support explainable path reconstruction.
- MUST support path depth limits.
- MUST prevent accidental infinite traversal.
- MUST allow criticality metadata on resources.
- SHOULD support edge confidence or evidence metadata.
- SHOULD support path deduplication.
- OPEN: exact graph schema and projection strategy.

## Attack-path requirements
- MUST produce reproducible results for the same snapshot and rule set.
- MUST identify rule/logic responsible for a finding.
- MUST explain each edge in a path.
- MUST avoid opaque LLM-only findings.
- SHOULD rank findings.
- SHOULD propose minimal remediation candidates.
- OPEN: exact scoring formula and graph algorithms.

## Runtime gateway requirements
- MUST authenticate the caller.
- MUST identify the acting principal when possible.
- MUST accept delegated context.
- MUST validate request schema.
- MUST support ALLOW, DENY, REQUIRE_APPROVAL.
- MUST generate reason codes.
- MUST audit every decision.
- MUST fail safely on policy evaluation errors.
- SHOULD support bounded decision latency.
- SHOULD support policy versioning.
- OPEN: synchronous HTTP, sidecar, proxy, or SDK deployment patterns.

## Delegation requirements
- MUST record delegator and delegate.
- MUST support chained delegation.
- MUST support expiration.
- MUST support scope/resource constraints.
- MUST prevent unapproved privilege amplification.
- SHOULD include purpose/intent metadata.
- SHOULD enable chain reconstruction.
- OPEN: exact cryptographic representation of delegated authority.

## Policy requirements
- MUST be versionable.
- MUST be testable.
- MUST separate policy from application code.
- MUST support explicit deny.
- SHOULD support structured reason output.
- SHOULD support environment-specific policy bundles.
- OPEN: Rego-only versus abstraction layer.

## Telemetry requirements
- MUST contain event type, time, principal, action, resource, decision, and reason where applicable.
- MUST avoid leaking secrets.
- MUST permit correlation using request/trace IDs.
- SHOULD export through OpenTelemetry-compatible mechanisms.
- SHOULD provide SIEM mapping examples.
- OPEN: storage/retention defaults.

## Dashboard requirements
- MUST display identities, findings, paths, and decisions.
- MUST distinguish facts from inferred edges visually or semantically.
- SHOULD allow graph exploration.
- SHOULD show evidence and remediation.
- SHOULD permit filtering by severity/type/provider.
- OPEN: exact frontend graph library and UX.

## Security-lab requirements
- MUST be isolated.
- MUST have explicit setup and teardown.
- MUST avoid targeting third-party systems.
- MUST use synthetic data.
- MUST have cost controls for cloud labs.
- SHOULD provide expected detections/results.
- SHOULD run at least partially in CI where practical.

## Documentation requirements
- MUST include architecture.
- MUST include threat model.
- MUST include setup.
- MUST include security policy.
- MUST include contribution workflow.
- MUST include design decisions for major changes.
- SHOULD include diagrams and demo scripts.

## Quality gates
A pull request affecting critical authorization or graph logic MUST:
- include tests
- document changed assumptions
- preserve explainability
- pass static analysis
- pass security checks
- be reviewed by the human owner before merge
