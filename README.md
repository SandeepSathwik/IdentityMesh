# IdentityMesh

**Identity security for humans, cloud workloads, and autonomous AI agents.**

IdentityMesh is an open-source security platform for discovering identities, modeling effective privilege, identifying attack paths, evaluating delegated authority, and enforcing runtime authorization across cloud, Kubernetes, and agentic environments.

> Status: Pre-alpha / active implementation
> Initial platform focus: AWS + Kubernetes + AI agents/MCP  
> Primary language: Python  
> Intended maturity: production-quality open-source portfolio project, not a tutorial or demo

## Current implementation

The repository currently provides the M0 platform foundation and the first bounded AWS
collector capability:

- FastAPI service with liveness and authenticated PostgreSQL/Neo4j readiness checks
- validated environment-based configuration and structured request/error handling
- PostgreSQL-owned snapshot lifecycle with atomic active-snapshot promotion
- Neo4j reserved as a rebuildable graph projection, as recorded in ADR-0001
- Alembic migrations applied before the API starts in Docker Compose
- read-only AWS IAM role collection using STS identity verification and paginated `ListRoles`
- explicit `complete`, `partial`, and `failed` collection results with safe reason codes
- deterministic unit tests and PostgreSQL integration tests in CI on Python 3.10 and 3.12

Normalization, graph projection, attack-path analysis, the dashboard, and runtime
authorization remain planned work. The collector is not yet exposed through the API or
connected to snapshot persistence.

## Local development

Requirements: Python 3.10 or newer, Docker, and Docker Compose.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
Copy-Item .env.example .env
docker compose up --build --detach --wait
```

Set unique local-only values for `POSTGRES_PASSWORD` and `NEO4J_PASSWORD` in `.env` before
starting the stack. The API is available at `http://127.0.0.1:8000`; verify it with:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

See the [Development Guide](docs/DEVELOPMENT.md) for migrations, tests, and teardown.

---

## Why IdentityMesh exists

Modern systems no longer contain only human users and service accounts. They increasingly include:

- Human identities
- Cloud IAM identities
- Kubernetes service accounts and workloads
- CI/CD identities
- Federated identities
- Autonomous or semi-autonomous AI agents
- MCP clients and servers
- Delegated access chains
- Short-lived machine credentials
- Runtime tool permissions

Security teams often lack a single view of:

1. **Who or what is acting?**
2. **What authority does it have?**
3. **Where did that authority come from?**
4. **What can it reach indirectly?**
5. **Can it escalate?**
6. **Can delegation increase privilege?**
7. **Should a requested action be allowed right now?**
8. **Can the decision be explained and audited?**

IdentityMesh is intended to answer those questions.

---

## Product vision

IdentityMesh should eventually support a flow like:

```text
Human / Workload / Agent
          |
          v
  Identity Discovery
          |
          v
   Normalized Model
          |
          v
   Identity Graph
          |
          v
  Attack Path Engine
          |
          v
Risk + Policy Evaluation
          |
          v
Runtime Authorization Gateway
          |
          v
Allow / Deny / Require Approval
          |
          v
Telemetry / SIEM / Investigation
```

The flagship demonstration for v1.0 is:

```text
Developer
    ↓
AI Agent
    ↓
MCP Tool
    ↓
AWS Role
    ↓
Kubernetes Workload
    ↓
Privileged IAM Role
    ↓
Production Secret
```

IdentityMesh should discover the relevant identities and relationships, identify the dangerous path, explain the risk, recommend remediation, enforce an equivalent runtime policy, emit telemetry, and display the result in the dashboard.

---

## Core capabilities

### 1. Identity discovery
Collect identities, roles, policies, bindings, credentials, trust relationships, agent metadata, tools, and delegation relationships.

### 2. Identity graph
Normalize the above into a graph that represents:
- ownership
- federation
- assumption
- impersonation
- delegation
- tool access
- role binding
- resource access
- effective privilege
- privilege escalation opportunities

### 3. Attack-path analysis
Find and explain paths from low-trust principals to sensitive resources or high-privilege identities.

### 4. Agent identity
Treat AI agents as first-class principals rather than anonymous processes.

### 5. Delegated authorization
Track who delegated authority, through which chain, for what purpose, for what resource, and for how long.

### 6. Runtime authorization
Evaluate sensitive tool or resource actions using identity, scope, policy, delegation, resource sensitivity, and contextual risk.

### 7. Security telemetry
Produce structured, explainable authorization and attack-path events suitable for SIEM ingestion.

### 8. Security labs
Provide deliberately vulnerable lab scenarios for validation, regression tests, demonstrations, and attack research.

---

## V1 scope

V1 prioritizes depth over breadth.

### In scope
- AWS IAM and selected AWS resource relationships
- Kubernetes RBAC and workload identity
- AI agent registry and tool permissions
- MCP-aware identity/tool modeling
- Neo4j-based identity graph
- Attack-path analysis
- Policy evaluation
- Allow / deny / require-approval decisions
- Delegation-chain validation
- Audit/event pipeline
- Splunk-compatible telemetry
- Local developer environment
- Terraform-based test infrastructure
- Automated tests and attack scenarios
- Web dashboard

### Explicitly out of scope for V1
- Full multi-cloud parity
- Full CNAPP/CSPM replacement
- Generic vulnerability scanning
- Custom SIEM
- Password management
- Endpoint protection
- Blockchain
- Custom graph database
- Custom policy language
- Training a custom LLM
- Supporting every agent framework
- Fully autonomous remediation in production

---

## Engineering principles

1. **Security decisions must be explainable.**
2. **Critical authorization decisions must be deterministic.**
3. **Delegation must not silently increase authority.**
4. **Least privilege is a design goal, not a dashboard label.**
5. **Runtime enforcement and passive analysis are separate concerns.**
6. **Every important security assertion should be testable.**
7. **Every collector must degrade safely on partial permissions or incomplete data.**
8. **The platform must distinguish observed facts from inferred relationships.**
9. **AI may assist analysis, but AI output must not be the sole basis for critical allow/deny decisions.**
10. **Implementation freedom is encouraged when contracts, invariants, and security goals remain satisfied.**

---

## Documentation map

- [Project Charter](docs/PROJECT_CHARTER.md)
- [Product Requirements](docs/PRD.md)
- [Scope and Non-Goals](docs/SCOPE.md)
- [System Requirements](docs/REQUIREMENTS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data Model](docs/DATA_MODEL.md)
- [Attack Path Engine](docs/ATTACK_PATH_ENGINE.md)
- [Policy Engine](docs/POLICY_ENGINE.md)
- [Risk Model](docs/RISK_MODEL.md)
- [Threat Model](docs/THREAT_MODEL.md)
- [Testing Strategy](docs/TESTING_STRATEGY.md)
- [Observability](docs/OBSERVABILITY.md)
- [Security Labs](docs/LABS.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [Roadmap](docs/ROADMAP.md)
- [Milestones](docs/MILESTONES.md)
- [Backlog](docs/BACKLOG.md)
- [Release Process](docs/RELEASE_PROCESS.md)
- [Governance](docs/GOVERNANCE.md)
- [Decision Log](docs/DECISION_LOG.md)
- [ADRs](docs/adr/README.md)
- [Security Policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)

---

## Repository direction

A likely structure is:

```text
identitymesh/
├── apps/
│   ├── api/
│   ├── dashboard/
│   └── gateway/
├── packages/
│   ├── identity-model/
│   ├── graph-engine/
│   ├── attack-paths/
│   ├── authorization/
│   ├── risk-engine/
│   ├── telemetry/
│   └── agent-security/
├── collectors/
│   ├── aws/
│   ├── kubernetes/
│   └── agents/
├── policies/
│   └── rego/
├── detections/
│   └── sigma/
├── labs/
│   ├── aws/
│   ├── kubernetes/
│   ├── mcp/
│   └── agent-attacks/
├── infrastructure/
│   ├── terraform/
│   ├── docker/
│   └── kubernetes/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   └── e2e/
├── benchmarks/
├── docs/
├── examples/
├── scripts/
├── CONTRIBUTING.md
├── SECURITY.md
└── README.md
```

This is a blueprint, not a rigid requirement. Coding agents may propose a different structure when there is a clear engineering reason.

---

## Definition of success

IdentityMesh v1.0 is successful when it can demonstrate:

- reliable identity discovery
- useful graph construction
- reproducible attack-path findings
- understandable privilege explanations
- agent identity and delegation
- runtime policy enforcement
- audit-grade telemetry
- realistic security lab scenarios
- automated regression tests
- clean setup and teardown
- architecture and security documentation
- a compelling end-to-end demo

The project should be explainable in a technical interview without relying on generated code as a black box.
