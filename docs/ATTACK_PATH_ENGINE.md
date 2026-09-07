# Attack Path Engine

## Purpose
The attack-path engine identifies transitive relationships that allow a lower-trust principal to obtain dangerous authority or reach sensitive resources.

## Design goals
- deterministic
- explainable
- reproducible
- modular
- testable
- provider-aware without hard-coding all logic into one module

## Example path

```text
Developer
  -> owns
Agent
  -> can_call
CloudTool
  -> assumes
DevRole
  -> can_pass_role
LambdaRole
  -> can_access
ProductionSecret
```

## Finding requirements
Every finding should include:
- title
- severity
- source principal
- target resource/privilege
- ordered path
- evidence
- rule ID
- explanation
- remediation guidance
- confidence where relevant
- snapshot ID
- detected_at

## Initial attack-path classes

### AWS
- role assumption chains
- broad trust
- cross-account trust
- PassRole opportunities
- admin policy reachability
- access to sensitive secrets
- workload role escalation

### Kubernetes
- service-account token use
- role binding escalation
- cluster-admin reachability
- namespace-to-cluster escalation
- workload identity pivot

### Agentic
- agent-to-tool privilege
- delegated authority amplification
- owner/agent scope mismatch
- agent-to-cloud escalation
- tool server excessive privilege
- confused-deputy patterns

## Rule architecture
Rules should be:
- versioned
- testable
- attributable
- separable from graph storage implementation where practical

Potential shape:

```text
Rule
- id
- title
- description
- prerequisites
- traversal/logic
- severity logic
- evidence requirements
- remediation template
- references
```

## Graph traversal
Potential approaches:
- Cypher path queries
- precomputed privilege edges
- bounded BFS/DFS
- graph projections
- rule-specific traversals

No single approach is mandated.

Agents should benchmark alternatives using representative datasets.

## Path explosion controls
The engine must protect against:
- cycles
- unbounded path length
- duplicate semantic paths
- combinatorial explosion
- noisy low-value findings

Potential controls:
- maximum depth
- edge allowlist per rule
- path deduplication
- node criticality filters
- graph projection
- dominance pruning
- risk thresholds

## Explainability
The engine should render each path step as a meaningful statement.

Bad:
```text
A -> B -> C -> D
```

Better:
```text
Developer Alice owns agent deploy-bot.
deploy-bot can call the AWS deployment tool.
The tool uses DevRole.
DevRole can pass LambdaAdminRole.
LambdaAdminRole can read ProductionSecret.
```

## Remediation
Prefer root-cause remediation over generic advice.

Examples:
- restrict role trust
- scope PassRole resources
- remove wildcard action
- bind workload to narrower role
- reduce agent tool scope
- constrain delegation
- require human approval

## Testing
Every attack-path rule should have:
- positive fixture
- negative fixture
- near-miss fixture
- cycle case where relevant
- missing-data behavior
- expected explanation

## Performance
Initial target:
- useful interactivity on small/medium lab datasets
- no premature distributed graph processing

Benchmark:
- node count
- edge count
- rule count
- analysis duration
- memory use
- finding count
- path deduplication effectiveness

## Open questions
- path scoring
- minimal cut/remediation suggestions
- temporal paths
- confidence model
- graph snapshots
- multi-provider joins
- incremental re-analysis
