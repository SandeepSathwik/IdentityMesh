# Security Policy

## Project maturity
IdentityMesh is expected to pass through experimental and pre-release stages before v1.0.

Until a stable release exists, do not assume the project is production-ready.

The current bearer-token data API is intentionally restricted by configuration to local and
test environments. It is not a production authentication design. The dashboard shell is
public but contains no identity data; every `/api/v1` data route requires the configured
token. Collectors use the standard provider credential chain and do not accept credentials in
API requests.

Snapshot comparisons use the same authentication and read retained complete evidence only.
They expose safe role references and changed field names, excluding raw trust-policy and tag
values. These observational differences are not authorization decisions or risk findings;
see [Inventory History](docs/INVENTORY_HISTORY.md) for completeness checks and residual limits.

## Reporting a vulnerability
For a real public repository, configure GitHub Private Vulnerability Reporting or a dedicated security contact before release.

Do not include real secrets or sensitive infrastructure data in reports.

## Security principles
- least privilege
- explicit trust boundaries
- deterministic critical authorization
- safe failure behavior
- auditability
- secure defaults
- no plaintext secret logging

## Supported security assumptions
Users are expected to:
- protect deployment credentials
- configure TLS where remotely accessible
- restrict database/network access
- use isolated test labs
- review policies before enforcing production decisions

## Out-of-scope security claims
IdentityMesh does not claim:
- perfect attack-path completeness
- complete provider coverage
- formal verification
- protection against every prompt-injection strategy
- replacement for provider-native IAM controls

## Secrets
Never:
- commit API keys
- commit cloud keys
- log bearer tokens
- store private keys in fixtures
- place real secrets in screenshots

Use synthetic examples.

## Cloud permissions
Collectors should use read-only or narrowly scoped permissions whenever possible.

A PR that broadens permissions must justify:
- why
- exact actions
- exact resources
- alternatives considered

## Runtime enforcement
Sensitive policy failures should fail closed by default.

Any fail-open path requires explicit documentation and review.

## Security testing
Security-sensitive releases should include:
- dependency scanning
- secret scanning
- SAST
- container scanning where applicable
- auth tests
- policy tests
- attack-path regression tests

## Responsible demonstrations
Labs and attack examples must target only:
- synthetic local systems
- explicitly created test infrastructure
- environments the operator controls

Do not build generalized attack automation against arbitrary third-party targets.
