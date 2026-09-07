# Security Labs

## Purpose
Labs make IdentityMesh demonstrable, testable, and credible.

Every lab should be safe, isolated, reproducible, and intentionally vulnerable.

## Lab principles
- synthetic identities and data
- isolated accounts/namespaces
- explicit setup
- explicit teardown
- cost warnings
- no third-party targets
- no persistence beyond documented test scope
- expected findings documented

## Proposed labs

### Lab 1: AWS AssumeRole path
Demonstrates trust relationship chaining.

### Lab 2: PassRole escalation
A development role can pass a more privileged role to a service.

Expected result:
IdentityMesh reports a path to sensitive resource access.

### Lab 3: Cross-account trust
A role in one account can indirectly reach a privileged role in another.

### Lab 4: Kubernetes RBAC escalation
A service account obtains broader control through bindings.

### Lab 5: EKS workload-to-AWS role
Maps Kubernetes workload identity to cloud resource access.

### Lab 6: Agent with excessive tool scope
An agent has a tool capable of production access beyond its declared purpose.

### Lab 7: Delegation amplification
A user delegates development scope, but a nested agent attempts production scope.

Expected:
runtime denial.

### Lab 8: Confused deputy
Low-privilege caller induces a privileged agent/tool to perform an unauthorized action.

### Lab 9: Indirect prompt injection
Synthetic document instructs an agent to access an unrelated secret.

Expected:
the tool request reaches authorization boundary and is denied.

### Lab 10: Malicious tool metadata
A tool/server advertises benign intent but attempts an additional sensitive operation.

## Lab directory convention

```text
labs/<lab-name>/
├── README.md
├── infrastructure/
├── fixtures/
├── expected/
├── attacks/
├── cleanup/
└── tests/
```

## Lab README requirements
Each lab must document:
- goal
- topology
- setup
- cost considerations
- credentials model
- attack
- expected graph
- expected finding
- expected runtime decision
- cleanup
- troubleshooting

## CI
Cloud labs may be too expensive for every PR.

Strategy:
- unit/mocked equivalents on every PR
- local container labs where possible
- scheduled or manually approved cloud integration runs

## Safety
Lab automation must require explicit target identifiers.
Avoid scripts that discover or attack arbitrary external resources.
