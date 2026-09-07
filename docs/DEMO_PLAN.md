# Flagship Demo Plan

## Goal
Demonstrate IdentityMesh in under 10 minutes without requiring the audience to understand implementation details.

## Story
A developer has legitimate development access.

The developer invokes an AI deployment agent.

The agent can call a cloud tool.

The cloud tool uses a role with a dangerous privilege path into a workload that can reach a production secret.

IdentityMesh should show this proactively and block an equivalent runtime request.

## Demo sequence

### 1. Environment
Show:
- developer
- agent
- MCP-like tool
- AWS role
- Kubernetes workload
- privileged role
- secret

### 2. Discovery
Run/trigger collection.

Show entities appearing.

### 3. Graph
Open attack graph.

Highlight path.

### 4. Finding
Show:
- critical severity
- each edge
- evidence
- root cause
- remediation

### 5. Agent action
Trigger synthetic agent request to read production secret.

### 6. Runtime decision
Show:
`DENY`

Reason:
delegated scope or policy violation.

### 7. Telemetry
Show security event and trace ID.

### 8. SIEM
Show corresponding event in Splunk-compatible view/dashboard.

### 9. Remediation
Apply narrower policy or remove dangerous edge.

### 10. Re-run
Finding disappears or risk drops.

## Demo quality bar
- deterministic
- fast
- no manual hidden fixes
- resettable
- synthetic data
- no real secrets
- screen-recordable
