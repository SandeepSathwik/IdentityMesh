# Development Guide

## Development philosophy
IdentityMesh should be developed as a real security product:
- issue-driven
- small reviewable changes
- automated tests
- documented decisions
- reproducible local environment

## Recommended environment
- Python 3.10 or newer
- Docker
- Docker Compose
- Git
- optional local Kubernetes
- Terraform
- Neo4j
- PostgreSQL

The current dashboard is packaged static HTML, CSS, and JavaScript and does not require
Node.js or a separate frontend toolchain.

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

## Current local setup

Create an isolated Python environment and install the locked dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

Copy `.env.example` to `.env` and set unique, local-only values for
`POSTGRES_PASSWORD`, `NEO4J_PASSWORD`, and `IDENTITYMESH_API_TOKEN`. The API token must contain
32–256 printable, non-whitespace ASCII characters. Set
`IDENTITYMESH_AWS_ALLOWED_ACCOUNT_ID` to the controlled 12-digit account that the read-only
collector may inspect. Do not reuse real database/API secrets or commit `.env`.

Start the API, PostgreSQL, and Neo4j:

```powershell
docker compose up --build --detach --wait
```

Compose runs Alembic migrations in a one-shot `migrate` service. The API starts only after
that service succeeds and Neo4j is healthy. A migration failure therefore prevents startup
instead of allowing the application to run against an incompatible schema.

The services bind only to the local loopback interface:

- API: `http://127.0.0.1:8000`
- Neo4j browser: `http://127.0.0.1:7474`
- Neo4j Bolt: `bolt://127.0.0.1:7687`
- PostgreSQL: `127.0.0.1:5432`

Verify authenticated dependency readiness:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

`/health/live` reports process liveness. `/health/ready` performs authenticated dependency
probes and returns `503` when PostgreSQL or Neo4j is unavailable; neither endpoint returns
connection strings or credentials.

Open `http://127.0.0.1:8000/` for the dashboard and enter the configured API token. The token
is retained only in page memory. The protected API can also be called directly:

```powershell
$headers = @{ Authorization = "Bearer $env:IDENTITYMESH_API_TOKEN" }
Invoke-RestMethod -Method Post -Headers $headers `
  http://127.0.0.1:8000/api/v1/collections/aws/iam/roles
Invoke-RestMethod -Headers $headers http://127.0.0.1:8000/api/v1/principals
```

The collection call uses the standard AWS credential chain and performs only
`sts:GetCallerIdentity` and paginated `iam:ListRoles`. Run live validation only with a
controlled account and the documented read-only permissions. Synthetic integration tests do
not require AWS credentials.

The current single-token data API is intentionally accepted only in `local` and `test`
environments. Do not expose it as a production authentication mechanism.

## Collect and inspect IAM users

Apply migrations to head, then use the dashboard's **Collect users** button, or:

```powershell
$run = Invoke-RestMethod -Method Post -Headers $headers `
  http://127.0.0.1:8000/api/v1/collections/aws/iam/users
Invoke-RestMethod -Headers $headers `
  "http://127.0.0.1:8000/api/v1/snapshots/$($run.snapshot_id)/users?limit=50"
```

User collection requires read-only `iam:ListUsers` in the configured controlled account.
It retains complete and partial observations separately from the active role graph; complete
user snapshots are collected, not ready. Live AWS validation remains owner-run. See
[AWS IAM user collection](AWS_USER_INVENTORY.md) for permissions, migration, and failure behavior.

## Compare retained observations

After two successful collections, select the base and target in the dashboard's **Compare
observations** panel. The earlier snapshot is the base. The API equivalent is:

```powershell
$query = "base_snapshot_id=$baseId&target_snapshot_id=$targetId&limit=50"
Invoke-RestMethod -Headers $headers "http://127.0.0.1:8000/api/v1/snapshots/compare?$query"
```

Set `$baseId` and `$targetId` from `GET /api/v1/snapshots`. Keep both IDs unchanged when using
`next_cursor` for later pages. Metadata differences do not establish access changes. See
[Inventory History](INVENTORY_HISTORY.md) for failure codes and scope. No migration is needed
for comparison of existing role snapshots.

For users, choose **Compare user observations** or use the same query parameters with
`GET /api/v1/snapshots/users/compare`. Both inputs must be complete user collections in the
same account and partition. No additional migration or AWS permission is needed. See
[IAM user inventory history](USER_INVENTORY_HISTORY.md) for semantics and error codes.

## Migrations

With `IDENTITYMESH_POSTGRES_DSN` set for the target database:

```powershell
alembic --config pyproject.toml upgrade head
```

Review every generated or hand-written migration. In particular, verify constraints,
downgrade consequences, locking behavior, and compatibility with retained snapshots.

## Quality checks

```powershell
ruff check .
ruff format --check .
mypy
pytest --cov --cov-report=term-missing
```

Snapshot, evidence, and graph integration tests require isolated PostgreSQL and Neo4j services;
PostgreSQL must be migrated to `head`:

```powershell
$env:IDENTITYMESH_TEST_POSTGRES_DSN = 'postgresql://user:password@127.0.0.1:5432/identitymesh_test'
$env:IDENTITYMESH_TEST_NEO4J_URI = 'bolt://127.0.0.1:7687'
$env:IDENTITYMESH_TEST_NEO4J_USERNAME = 'neo4j'
$env:IDENTITYMESH_TEST_NEO4J_PASSWORD = 'local-test-only'
$env:IDENTITYMESH_POSTGRES_DSN = $env:IDENTITYMESH_TEST_POSTGRES_DSN
alembic --config pyproject.toml upgrade head
Remove-Item Env:IDENTITYMESH_POSTGRES_DSN
pytest --cov --cov-report=term-missing
```

Set `IDENTITYMESH_POSTGRES_DSN` only for the migration command; remove it before the test
command so configuration-isolation tests do not inherit runtime dependency settings. Keep
the `IDENTITYMESH_TEST_*` variables set for integration tests.

Do not point the test variable at a database containing data that must be retained. AWS
collector tests use synthetic protocol-backed responses and require no cloud credentials.

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
5. contributor proposes approach
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
When proposed code fails:
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
