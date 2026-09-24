# Flagship Demo Plan

## Goal
Demonstrate IdentityMesh in under 10 minutes without requiring the audience to understand implementation details.

Status: future v1 flagship demo. The current demonstrable flow ends at authenticated AWS role
collection, verified node projection, dashboard inventory, and observed snapshot comparison; it does not yet include paths,
findings, enforcement, or SIEM output.

## Current inventory-history demonstration

After two controlled-account role collections reach `ready`, connect to the dashboard and
choose the older and newer snapshots in **Compare observations**. Show counts and evidence
references, then explain that metadata differences do not establish effective access. A failed
collection is excluded from the choices. Reversing the pair produces an explicit order error.
The API supports the same flow and pagination. Automated tests exercise synthetic examples
without changing AWS; live validation remains owner-run in the allowlisted account.

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
