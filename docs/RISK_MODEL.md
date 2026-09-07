# Risk Model

## Goal
Prioritize findings using transparent, reproducible signals.

Risk scoring should help order work. It should not pretend to be mathematically exact.

## Principles
- deterministic for the same inputs
- explainable
- evidence-backed
- configurable
- not dependent solely on LLM judgment
- avoid false precision

## Candidate signals

### Impact
- target resource criticality
- production versus development
- administrative privilege
- secret access
- destructive action potential
- cross-account reach

### Exploitability
- path length
- number of required conditions
- credential availability
- trust breadth
- role assumption feasibility
- need for human interaction
- runtime constraints

### Exposure
- internet/external origin
- human breadth
- agent/tool exposure
- long-lived credentials
- public or shared principals

### Control weakness
- missing approval
- wildcard actions
- wildcard resources
- weak trust conditions
- missing delegation context
- excessive tool scope

## Suggested score bands
The exact formula is open.

Suggested output:
- Critical
- High
- Medium
- Low
- Informational

A numerical score may be included for sorting, but the severity label and contributing factors must be visible.

## Example explanation

```text
Severity: Critical

Contributing factors:
+ target is production secret
+ path ends in administrative role
+ wildcard PassRole permission
+ no approval boundary
- path requires authenticated developer session
```

## Agent security score
If an overall agent security score is implemented, it must be explainable and decomposable.

Possible dimensions:
- identity strength
- credential hygiene
- authorization scope
- delegation controls
- tool exposure
- production reachability
- runtime enforcement
- auditability

Do not publish a single number without showing contributing factors.

## Remediation priority
Where possible, distinguish:
- risk severity
- remediation cost
- blast-radius reduction

A lower-cost change that removes multiple attack paths may be prioritized.

## Open questions
- exact weighting
- path length effect
- confidence
- historical behavior
- control effectiveness
- graph centrality
- business metadata integration

Any scoring change that materially changes severity should be versioned.
