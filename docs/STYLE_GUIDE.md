# Documentation and Code Style Guide

## Documentation
Write for engineers.

Prefer:
- concrete statements
- explicit assumptions
- examples
- diagrams
- constraints
- rationale

Avoid:
- marketing filler
- claims without evidence
- unexplained acronyms
- copying vendor language
- pretending an experimental feature is production-ready

## Security findings
Use:
- title
- severity
- evidence
- path
- impact
- remediation
- limitations

## Code
Prefer:
- clear names
- small interfaces
- typed models
- explicit side effects
- composition
- dependency injection where it helps testing

Avoid:
- abstraction for its own sake
- giant modules
- hidden global state
- swallowing exceptions
- dynamic magic in security-critical logic

## Naming
Use domain terms consistently:
- principal
- resource
- permission
- policy
- delegation
- relationship
- finding
- decision
- evidence
- snapshot

## Comments
Explain:
- security rationale
- provider quirks
- non-obvious invariants
- why a workaround exists

Do not comment obvious syntax.
