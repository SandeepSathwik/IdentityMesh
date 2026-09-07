# Security Review Checklist

Use for security-sensitive PRs.

## Identity
- Is the acting principal authenticated?
- Is identity provenance clear?
- Is ownership trusted or user-controlled?
- Can an identity be spoofed?

## Authorization
- Is deny behavior tested?
- Can privilege increase unexpectedly?
- Are missing policies safe?
- Are policy errors safe?
- Is the decision explainable?

## Delegation
- Is the original subject retained?
- Can a downstream principal widen scope?
- Is expiration enforced?
- Can delegation be replayed?
- Is the chain auditable?

## Secrets
- Any new secret storage?
- Any log leakage?
- Any test fixtures containing real secrets?
- Are tokens redacted?

## Cloud
- Did permissions expand?
- Are resources scoped?
- Could collector writes occur?
- Is partial permission handled?

## API
- Input validated?
- Authz checked?
- SSRF risk?
- Injection risk?
- Graph query abuse?
- Rate-limit concern?

## Data
- Is source provenance retained?
- Is stale data distinguishable?
- Are destructive migrations safe?

## Supply chain
- New dependency justified?
- Maintained?
- Pinned?
- Known vulnerabilities?

## Observability
- Audit event emitted?
- Request/trace ID?
- Sensitive values excluded?

## Tests
- Positive
- Negative
- abuse case
- malformed input
- regression test

## Documentation
- threat model updated?
- architecture updated?
- ADR needed?
