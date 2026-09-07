# Development Guide

## Development philosophy
IdentityMesh should be developed as a real security product:
- issue-driven
- small reviewable changes
- automated tests
- documented decisions
- reproducible local environment

## Recommended environment
- Python supported stable release
- Docker
- Docker Compose
- Git
- optional local Kubernetes
- Terraform
- Node.js for dashboard
- Neo4j
- PostgreSQL

Exact versions should be pinned in project configuration rather than this document.

## Local development target
Aim for a short workflow such as:

```bash
make dev
make test
make lint
make security
make down
```

The exact task runner may differ.

## Current M0 setup

Create an isolated Python environment and install the locked dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

Copy `.env.example` to `.env` and set unique, local-only values for
`POSTGRES_PASSWORD` and `NEO4J_PASSWORD`. Do not reuse real credentials.

Start the API, PostgreSQL, and Neo4j:

```powershell
docker compose up --build --detach --wait
```

The services bind only to the local loopback interface:

- API: `http://127.0.0.1:8000`
- Neo4j browser: `http://127.0.0.1:7474`
- Neo4j Bolt: `bolt://127.0.0.1:7687`
- PostgreSQL: `127.0.0.1:5432`

Verify authenticated dependency readiness:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

Stop the services while retaining local database volumes:

```powershell
docker compose down
```

To intentionally delete all local IdentityMesh database data, add `--volumes`.
This cleanup command must not be used for an environment containing data that
needs to be retained.

## Branch model
Suggested:
- `main` protected
- short-lived feature branches
- PR for all material changes

Avoid long-running branches.

## Commit style
Prefer clear commits:
- feat:
- fix:
- security:
- test:
- docs:
- refactor:
- chore:

Conventional commits are optional unless adopted formally.

## Coding standards
- type hints
- explicit interfaces
- no secrets in code
- structured errors
- input validation
- predictable naming
- no silent exception swallowing
- comments explain why, not obvious syntax

## Dependency policy
- justify large dependencies
- pin versions
- monitor vulnerabilities
- remove unused packages
- prefer maintained libraries
- avoid copying security-critical snippets without understanding them

## Configuration
- environment-based configuration
- checked-in example configuration
- safe defaults
- validation at startup
- no secret values in sample files

## Database changes
Use migrations.

A schema change should include:
- migration
- rollback consideration
- tests
- compatibility notes

## Feature workflow
1. create issue
2. define objective
3. define acceptance criteria
4. list security constraints
5. coding agent proposes approach
6. implement
7. test
8. security review
9. human review
10. merge
11. update docs/changelog when relevant

## Refactoring
Refactoring is encouraged when:
- complexity is demonstrably reduced
- behavior remains covered
- interfaces improve
- security reasoning improves

Avoid giant speculative rewrites.

## Debugging
When agent-generated code fails:
1. capture exact error
2. reproduce minimally
3. identify violated assumption
4. add regression test
5. fix root cause
6. document surprising behavior

## Documentation rule
If a feature changes:
- architecture
- public API
- security model
- setup
- policy behavior
- graph semantics

the relevant docs must change in the same PR.
