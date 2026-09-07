# Release Process

## Goals
Releases should be reproducible, documented, and security-reviewed.

## Versioning
Use semantic versioning when public APIs stabilize.

Pre-1.0:
- v0.1 identity core
- v0.2 attack paths
- v0.3 Kubernetes
- v0.4 agent identity
- v0.5 runtime control
- v0.6 adversarial labs
- v1.0 flagship release

## Pre-release checklist
- CI green
- unit/integration/security tests green
- dependency scan reviewed
- secret scan reviewed
- migration path tested
- docs updated
- changelog updated
- threat model reviewed for major security changes
- sample environment validated
- critical issues reviewed
- demo tested from clean setup

## Release artifacts
Potential:
- source tag
- container images
- SBOM
- checksums
- release notes
- deployment examples
- sample configuration

Exact signing strategy may evolve.

## Release notes
Include:
- highlights
- breaking changes
- security changes
- migrations
- known limitations
- fixed issues
- contributors

## Security release
Critical vulnerability fixes may use an expedited path, but tests and auditability should not be skipped.

## Rollback
Document:
- database migration rollback or forward-fix strategy
- policy rollback
- container rollback
- infrastructure rollback

## V1 quality gate
Do not call the project 1.0 simply because 12 months elapsed.

V1 requires:
- coherent end-to-end demo
- stable core schema/API
- repeatable attack-path results
- runtime enforcement
- security labs
- documentation
- predictable setup
