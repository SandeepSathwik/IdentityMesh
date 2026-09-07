# Scope and Non-Goals

## Scope philosophy
IdentityMesh is intentionally ambitious, but V1 must remain coherent. Every feature should strengthen at least one of four pillars:

1. identity visibility
2. attack-path understanding
3. delegated authorization
4. runtime enforcement

Features outside those pillars require strong justification.

## V1 in scope

### AWS
Priority entities and relationships:
- IAM users
- groups
- roles
- managed and inline policies
- trust policies
- instance profiles
- selected resource policies
- OIDC providers
- role assumption
- PassRole-relevant relationships
- selected Secrets Manager access
- selected Lambda/EKS role relationships
- cross-account trust where feasible

### Kubernetes
- namespaces
- service accounts
- roles
- cluster roles
- role bindings
- cluster role bindings
- pods/workloads
- service-account usage
- selected cloud workload identity mapping

### AI agents
- agent identity
- agent owner/operator
- agent purpose
- tool inventory
- MCP-like server/tool relationships
- delegated identity context
- credentials/scopes metadata
- runtime requests

### Graph and analysis
- normalized identity/resource graph
- critical-resource labeling
- role assumption paths
- PassRole-like paths
- transitive privilege
- delegation paths
- workload-to-cloud identity relationships
- agent-to-tool-to-cloud relationships

### Runtime enforcement
- authorization API/gateway
- allow
- deny
- require approval
- reason codes
- policy evaluation
- audit records
- delegation validation

### Telemetry
- structured events
- OpenTelemetry-friendly export
- Splunk-compatible output
- security event examples
- Sigma rules for selected events

### Labs
- intentionally vulnerable AWS lab
- Kubernetes RBAC lab
- agent/MCP lab
- prompt-injection/control-bypass scenarios in isolated environments
- privilege escalation labs that remain safe and non-deployable to unintended targets

## V1 out of scope

### Platform breadth
- Azure parity
- GCP parity
- SaaS identity discovery across dozens of providers

### Security category expansion
- vulnerability management platform
- endpoint security
- anti-malware
- DLP platform
- secrets vault
- full SIEM
- full SOAR
- full CSPM
- full CNAPP
- identity provider

### AI scope
- model training
- general-purpose chatbot
- autonomous remediation without approval
- arbitrary prompt classification as a core security control
- LLM-only authorization

### Enterprise features
- complex billing
- marketplace
- enterprise SSO matrix
- full multi-tenancy
- large-scale HA
- geo-distributed deployment
- formal compliance certification

## Scope decision rule
A proposed feature should answer "yes" to at least two:
- Does it materially improve identity visibility?
- Does it improve effective privilege or attack-path reasoning?
- Does it strengthen delegated authorization?
- Does it strengthen runtime prevention?
- Does it create important evidence for security operations?
- Does it materially improve reproducibility or security testing?

If not, defer it.

## Deferred opportunities
Potential post-V1 areas:
- Azure
- GCP
- GitHub/OIDC CI/CD identity
- identity posture analytics
- time-bound privilege
- auto-remediation PRs
- approval integrations
- additional policy engines
- advanced temporal graph analysis
- workload identity federation
- agent reputation/behavior baselining
- enterprise tenancy
