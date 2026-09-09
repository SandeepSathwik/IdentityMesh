# Repository File Manifest

This manifest summarizes the current public repository structure. It is descriptive, not an
architectural constraint; use `git ls-files` for the authoritative file list.

## Application and tests

- `src/identitymesh/` — API, configuration, dependency health, snapshots, collectors,
  provider-neutral principal contracts, and normalizers
- `tests/` — unit and PostgreSQL integration tests
- `migrations/` — Alembic environment and schema revisions

## Runtime and tooling

- `compose.yaml` — loopback-bound local PostgreSQL, Neo4j, migration, and API services
- `Dockerfile` — application image
- `pyproject.toml` — package metadata and tool configuration
- `requirements.lock` — reproducible Python dependency set
- `.env.example` — non-secret configuration template
- `.github/workflows/ci.yml` — Python quality and PostgreSQL integration workflow

## Public project documentation

- `README.md` — project overview, current status, and quick start
- `CONTRIBUTING.md` — contribution and validation expectations
- `SECURITY.md` — vulnerability reporting policy
- `CODE_OF_CONDUCT.md` — community conduct
- `docs/` — product, architecture, security, testing, development, and planning references
- `docs/adr/` — accepted and proposed architecture decision records
- `.github/ISSUE_TEMPLATE/` and `.github/PULL_REQUEST_TEMPLATE.md` — contribution templates

Local-only workspace guidance and intentionally untracked material are excluded from this
public manifest.
