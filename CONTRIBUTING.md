# Contributing to IdentityMesh

## Welcome
IdentityMesh welcomes contributions in:
- collectors
- identity modeling
- graph analysis
- authorization
- security labs
- detection content
- testing
- documentation
- performance
- frontend UX

## Before contributing
Read:
- README.md
- docs/PROJECT_CHARTER.md
- docs/ARCHITECTURE.md
- docs/THREAT_MODEL.md
- docs/TESTING_STRATEGY.md

## Contribution flow
1. select or open an issue
2. agree on scope for large work
3. create a focused branch
4. implement with tests
5. update docs
6. open a PR
7. address review
8. merge after required checks

## Pull request expectations
PRs should explain:
- what problem is solved
- how
- why this approach
- security implications
- tests
- limitations
- screenshots for UI changes

## Security-sensitive contributions
Changes affecting:
- auth
- policy
- delegation
- graph privilege semantics
- secrets
- cloud permissions
- approval
- audit integrity

require heightened review.

## Design changes
Major architectural changes should use an ADR.

## Code style
Follow project tooling.

General expectations:
- typed Python
- readable code
- explicit interfaces
- secure defaults
- test coverage
- minimal unnecessary dependencies

## Tests
A bug fix should include a regression test where practical.

Run the current local quality suite with:

```powershell
ruff check .
ruff format --check .
mypy
pytest --cov --cov-report=term-missing
```

PostgreSQL snapshot integration tests run when `IDENTITYMESH_TEST_POSTGRES_DSN` points to a
dedicated migrated test database. CI provisions this database and runs the complete suite.

A security rule should include:
- positive
- negative
- edge-case tests

## Documentation
Public behavior must be documented.

## Security issues
Do not open a public issue for a vulnerability that could meaningfully endanger users.
See SECURITY.md.

## Generated contributions
AI-assisted code is allowed.

Contributors are responsible for:
- correctness
- license compatibility
- security
- tests
- understanding the submitted code
