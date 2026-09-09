# Decision Log

Use this lightweight log for smaller decisions that do not require a full ADR.

| Date | Decision | Reason | Owner | Follow-up |
|---|---|---|---|---|
| 2026-09-09 | AWS is the first cloud provider | Depth before multi-cloud breadth | Project owner | Revisit after v1.0 |
| 2026-09-09 | Python is the primary backend language | Strong ecosystem and project fit | Project owner | Revisit only with evidence |
| 2026-09-09 | Neo4j is the initial graph database | Natural fit for attack-path analysis | Project owner | Benchmark before v1.0 |
| 2026-09-09 | OPA/Rego is the planned initial policy engine | Mature policy-as-code model; integration is not implemented | Project owner | ADR before integration |
| 2026-09-09 | Critical authorization is deterministic | Security and explainability | Project owner | Never weaken without ADR |
| 2026-09-09 | LLMs are advisory, not final authority | Avoid opaque critical decisions | Project owner | Reassess only with explicit design |
| 2026-09-09 | PostgreSQL owns evidence and snapshot state; Neo4j is a rebuildable projection | Avoid competing sources of truth and unsafe partial writes | Project owner | [ADR-0001](adr/0001-persistence-and-snapshot-projection.md) |
| 2026-09-09 | The first AWS increment uses a protocol boundary over Boto3 STS and IAM clients | Keep provider access replaceable and tests credential-free | Engineering | Revisit when a second AWS capability exposes a broader abstraction need |
