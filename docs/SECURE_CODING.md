# Secure Coding Standard

## Input
Treat all external input as untrusted:
- HTTP
- provider APIs
- policy files
- graph query parameters
- MCP/tool metadata
- agent messages
- uploaded configuration

Use explicit validation.

## Authentication
- use established libraries
- avoid custom crypto
- validate issuer/audience/expiration where applicable
- do not trust headers supplied by arbitrary clients for principal identity

## Authorization
- enforce server-side
- centralize sensitive policy decisions
- explicit deny
- no client-controlled privilege fields
- preserve original subject and acting principal

## Secrets
- environment/secret manager
- never source control
- redact logs
- synthetic fixtures only

## Cloud
- read-only collectors where possible
- scoped roles
- no wildcard permissions without documented need
- separate lab and development accounts/environments

## Database
- parameterized queries
- migrations
- constrained DB users
- avoid constructing raw Cypher from untrusted strings

## HTTP
- validate URLs
- SSRF defenses for any fetch capability
- timeouts
- size limits
- safe redirects
- appropriate CORS

## Serialization
- avoid unsafe pickle-like deserialization
- strict schemas for security-critical requests

## Files
- validate paths
- prevent path traversal
- limit upload types/size if uploads are added

## Dependencies
- minimize
- pin
- scan
- review maintenance health
- document major new dependencies

## Logging
Never include:
- credentials
- bearer tokens
- private keys
- full secret resource contents
- unnecessary PII

## Error handling
Return safe errors to clients.
Log enough for diagnosis without exposing sensitive content.

## Concurrency
Security state updates should consider:
- stale decisions
- double approval
- duplicate requests
- race conditions around revocation

## Supply chain
CI should include:
- secret scanning
- dependency scanning
- SAST
- container scanning as images are introduced
- SBOM for releases when practical

## Contributed-code review
All contributed code must receive normal review.
Pay special attention to:
- invented APIs
- insecure defaults
- excessive permissions
- dependency hallucinations
- shallow tests
- unsafe shell commands
