# Open Questions

These questions are intentionally unresolved. Contributors should treat them as opportunities
for engineering research, prototypes, benchmarks, and ADRs.

## Architecture
- Modular monolith or early service split?
- What should run synchronously versus in workers?
- Is Redis needed before scale justifies it?
- What is the cleanest deployment boundary for the runtime gateway?
- What validation must a Neo4j projection pass before an authoritative PostgreSQL snapshot is promoted?
- What retention and cleanup policy should apply to evidence, failed snapshots, and old graph projections?

## Graph
- Which labels and relationship types produce the clearest model?
- Store provider-native edges, normalized edges, or both?
- How should inferred edges be versioned?
- Cypher-only rules versus application-layer graph algorithms?
- How should equivalent paths be deduplicated?
- How should cycles be represented?
- What maximum path depth is useful?
- How should stale edges affect confidence?

## Identity
- How should a principal be globally identified across providers?
- How should identity aliases be reconciled?
- What does "owner" mean for an AI agent?
- How should CI/CD identity fit the model?
- Should credentials be first-class graph nodes?

## Agent identity
- How is agent identity issued?
- How is an agent bound to its workload?
- How are tools discovered?
- How should dynamic tools be represented?
- How is purpose represented without trusting arbitrary text?
- How is agent-to-agent delegation conveyed?
- How is the original human subject preserved across hops?

## Delegation
- Is delegation represented as a signed token, server-side state, or both?
- How are resource scopes expressed?
- How are nested scopes intersected?
- How does revocation work?
- How is replay prevented?
- Should a delegation have a maximum hop count?

## Runtime enforcement
- Proxy, sidecar, SDK, middleware, or multiple integration modes?
- What latency target is reasonable?
- Which requests should require fresh graph state?
- How should outage behavior differ by risk tier?
- How should approval tokens work?

## Policy
- OPA/Rego directly or an internal policy abstraction?
- How are policy bundles versioned?
- How are conflicts resolved?
- How should policy and graph-derived risk interact?
- Can policy simulation show "what would happen" before deployment?

## Risk
- Severity formula?
- Should path length reduce exploitability?
- How should business criticality be supplied?
- How should confidence from incomplete collection be represented?
- Can remediation impact be estimated?

## AWS
- Which provider APIs offer the best coverage with read-only permissions?
- How much effective-policy evaluation should V1 attempt?
- How should service-linked roles be treated?
- Which resource policies are worth implementing first?
- How should permission boundaries/SCP-like constraints be modeled?

## Kubernetes
- Which RBAC escalation primitives deserve V1 support?
- How should workload identity be joined to AWS?
- How should namespace boundaries influence risk?

## Telemetry
- What event schema best balances portability and richness?
- Which events deserve Sigma content?
- How should event retention work?
- Is append-only audit storage needed for V1?

## User experience
- Graph-first or finding-first dashboard?
- How much raw policy should be visible?
- What is the best way to explain a path?
- How should partial-data warnings be presented?

## Performance
- How large a graph should local V1 support?
- When do incremental graph updates outperform rebuilds?
- Which queries dominate latency?

## Research method
For any material open question:
1. define hypothesis
2. build smallest prototype
3. benchmark or test
4. document result
5. make decision
6. create ADR when consequential
