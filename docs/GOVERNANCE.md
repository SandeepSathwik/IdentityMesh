# Governance

## Project model
Initially, IdentityMesh is owner-led.

The human maintainer owns:
- product direction
- final security decisions
- release acceptance
- scope
- public claims
- risk acceptance

Maintainers and contributors may propose changes.

## Decision categories

### Routine implementation
Can be handled in normal PR review.

Examples:
- helper library
- query optimization
- UI component
- internal refactor
- test framework

### Significant design
Requires ADR.

Examples:
- graph schema model
- new policy engine
- service split
- public API redesign
- event format
- multi-tenancy

### Security-critical
Requires explicit human approval.

Examples:
- auth
- authorization
- delegation
- crypto
- secrets
- cloud permissions
- fail-open behavior
- approval bypass

## Principles
- prefer written decisions
- optimize for long-term clarity
- reject feature creep
- keep security claims conservative
- do not hide known limitations

## Roadmap changes
The roadmap may change when justified by:
- technical discovery
- security risk
- ecosystem changes
- implementation cost
- stronger product opportunity

Changes should preserve the project mission.
