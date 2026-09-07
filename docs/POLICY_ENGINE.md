# Policy and Runtime Authorization

## Objective
Provide deterministic runtime authorization for sensitive actions using identity, delegation, scope, resource, and context.

## Decision model
V1 decisions:

- `ALLOW`
- `DENY`
- `REQUIRE_APPROVAL`

Optional future:
- `ALLOW_WITH_CONSTRAINTS`
- `CHALLENGE`
- `DEFER`

## Evaluation inputs
Potential fields:
- principal
- principal type
- original subject
- acting agent
- delegation chain
- action
- resource
- requested scope
- environment
- purpose
- session
- time
- resource criticality
- trust/risk context
- policy version

## Evaluation output

```json
{
  "decision": "DENY",
  "reason_code": "DELEGATION_SCOPE_EXCEEDED",
  "policy_id": "agent-prod-access-v3",
  "policy_version": "3",
  "explanation": "The agent requested production access outside the delegated development scope.",
  "audit_id": "..."
}
```

## Initial policy engine
Default direction:
- OPA
- Rego

This is a starting point. If implementation experience identifies major shortcomings, alternatives may be evaluated and documented through ADRs.

## Policy design principles
- explicit deny takes precedence where appropriate
- high-risk production access should require stronger conditions
- delegation should narrow authority by default
- machine-readable reason codes are mandatory
- policy tests are mandatory
- policies should be version-controlled
- policy changes should be auditable

## Example policy concepts

### Agent purpose restriction
An invoice agent may not query production customer records.

### Delegation ceiling
A downstream agent cannot request a scope broader than its parent delegation.

### High-risk action
Actions such as broad IAM modification may require human approval even if technically permitted.

### Environment separation
Development identities should not directly access production resources.

## Approval flow
The platform should support `REQUIRE_APPROVAL` without hard-coding a specific approval provider.

Conceptual flow:

```text
Request
  ↓
Policy
  ↓
REQUIRE_APPROVAL
  ↓
Approval object created
  ↓
Human decision
  ↓
Short-lived authorization
```

V1 may implement a simple internal approval mechanism.

## Fail behavior
Policy evaluation failure must be explicit.

Sensitive actions should normally fail closed.

If a future use case requires fail-open, it must be:
- explicit
- scoped
- auditable
- documented
- prohibited for designated critical actions

## Policy testing
Each policy should include:
- allowed case
- denied case
- approval case if relevant
- malformed input
- missing delegation
- expired delegation
- privilege amplification case

## LLM use
LLMs may:
- draft policy suggestions
- summarize decisions
- explain findings
- propose remediation

LLMs must not:
- directly grant production access
- override policy without explicit authorized workflow
- invent identity facts
- silently change enforcement behavior

## Open design space
- policy bundle distribution
- policy cache
- policy composition
- resource hierarchy
- conflict resolution
- approval tokens
- signed delegation
- policy authoring UX
