# Observability and Security Telemetry

## Goals
Observability must support:
- debugging
- performance analysis
- auditability
- security investigation
- demo transparency

## Signals

### Logs
Structured logs preferred.

Include:
- timestamp
- service
- severity
- request ID
- trace ID
- event/action
- result
- safe metadata

Never log:
- secret values
- raw tokens
- passwords
- private keys

### Metrics
Candidate metrics:
- collector duration
- collector errors
- entities discovered
- edges generated
- findings created
- path analysis duration
- policy evaluation latency
- allow/deny/approval counts
- gateway errors
- approval duration
- event export failures

### Traces
Use tracing around:
- collector calls
- normalization
- graph updates
- attack-path analysis
- runtime authorization
- approval flow
- event export

## Security event schema
A common event envelope should include:

```text
event_id
event_type
timestamp
principal
acting_principal
original_subject
agent
action
resource
decision
reason_code
risk
policy_id
policy_version
delegation_chain
trace_id
source
metadata
```

Fields may evolve.

## Event types
Possible:
- identity.discovered
- identity.changed
- relationship.changed
- finding.created
- finding.resolved
- authorization.allowed
- authorization.denied
- authorization.approval_required
- approval.granted
- approval.denied
- delegation.created
- delegation.rejected
- policy.changed
- collector.partial_failure

## OpenTelemetry
Preferred standard for instrumenting services.

Exact collector/exporter topology is intentionally open.

## Splunk integration
Provide:
- sample sourcetype/index recommendations
- field mappings
- dashboards
- saved searches
- example Sigma rules where useful

Do not require Splunk to run the core project locally.

## Audit integrity
Security-relevant audit records should:
- be immutable or append-oriented where practical
- include actor
- include timestamp
- include policy version
- include decision
- support correlation

## Retention
V1 may use pragmatic defaults.
Retention configuration should be documented.

## Privacy
Avoid collecting unnecessary identity attributes.
Prefer security-relevant metadata only.
