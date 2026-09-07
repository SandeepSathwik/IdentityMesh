# Threat Model

## Purpose
This document defines security assumptions, assets, trust boundaries, adversaries, and major threat classes for IdentityMesh.

It is expected to evolve throughout development.

## Security objectives

IdentityMesh should protect:
- authorization integrity
- identity graph integrity
- provider credentials
- policy integrity
- delegation integrity
- audit integrity
- security findings
- resource metadata
- user/session data

## High-value assets
- collector credentials
- policy bundles
- runtime authorization endpoint
- delegation records/tokens
- agent registry
- graph database
- audit logs
- cloud metadata
- approval tokens
- administrator sessions

## Trust boundaries
1. external provider APIs
2. cloud account boundary
3. Kubernetes cluster
4. agent runtime
5. tool/MCP server
6. authorization gateway
7. policy engine
8. database boundary
9. dashboard/API boundary
10. observability pipeline
11. CI/CD
12. lab infrastructure

## Adversaries

### Compromised human identity
Attempts to use legitimate access to escalate.

### Compromised workload
Attempts to access broader cloud permissions.

### Malicious or manipulated AI agent
Attempts dangerous tool calls.

### Malicious tool server
Misrepresents functionality or abuses credentials.

### External attacker
Attempts API exploitation, credential theft, or remote access.

### Insider
Abuses legitimate configuration access.

### Supply-chain attacker
Compromises a dependency, image, action, or build artifact.

## Major threats

### T1 Privilege escalation
A low-privilege identity obtains more authority through trust, role assumption, PassRole, RBAC, delegation, or tool credentials.

### T2 Confused deputy
A lower-privilege actor convinces a higher-privilege agent/service to perform unauthorized work.

### T3 Delegation amplification
Each hop appears valid individually but the final authority exceeds the original subject.

### T4 Prompt injection
Malicious content attempts to manipulate an agent into unauthorized tool access.

### T5 Tool poisoning
A tool or server description induces inappropriate action or hides side effects.

### T6 Credential theft
Attacker obtains a workload or agent token.

### T7 Token replay
A valid token is used from an unintended context.

### T8 Graph poisoning
Collected or ingested data is manipulated to create false relationships or hide real ones.

### T9 Policy tampering
An attacker modifies enforcement rules.

### T10 Fail-open behavior
Policy/gateway error inadvertently grants access.

### T11 Audit suppression
Attacker performs actions without reliable event generation.

### T12 Secret leakage
Credentials or sensitive resource values enter logs or traces.

### T13 Dashboard/API exploitation
Injection, auth bypass, SSRF, broken access control, or unsafe graph queries.

### T14 Supply-chain compromise
Malicious dependency or CI action alters code/builds.

### T15 Lab escape / misconfiguration
Test infrastructure affects unintended systems or incurs uncontrolled cost.

## Security controls

### Identity
- authenticated callers
- explicit principal type
- scoped credentials
- short-lived credentials where feasible

### Authorization
- policy-as-code
- explicit deny
- fail-closed for sensitive operations
- delegation ceiling
- approval for selected actions

### Data
- no plaintext secret logging
- encryption in transit
- restricted database access
- provenance

### Software
- dependency scanning
- secret scanning
- SAST
- container scanning
- signed/reproducible artifacts where practical
- CI protection

### Detection
- authorization event logging
- graph change events
- policy change events
- high-risk path findings
- agent-denial telemetry

## Abuse cases to test
- agent asks for secret outside purpose
- nested agent requests broader privilege
- user with dev access invokes prod-capable agent
- malicious MCP server requests extra scopes
- role trust broadens unexpectedly
- collector loses permission
- graph contains stale relationship
- policy engine unavailable
- approval token reused
- resource criticality mislabeled
- cloud account returns partial data

## LLM-specific safety boundary
LLMs are untrusted reasoning assistants.

They may transform or summarize security context, but critical truth must come from:
- provider evidence
- normalized data
- deterministic rules
- explicit policy
- human-approved configuration

## Threat modeling process
For each major feature:
1. identify assets
2. identify trust boundaries
3. identify abuse cases
4. define security invariants
5. add tests
6. document residual risk

Major threat-model changes should be reviewed before release.
