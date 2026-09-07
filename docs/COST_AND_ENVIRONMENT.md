# Environment and Cost Controls

## Goals
Cloud labs must remain:
- isolated
- affordable
- easy to destroy
- difficult to deploy accidentally into the wrong account

## Environments
Suggested:
- local
- test
- cloud-lab
- optional staging

Do not begin with production.

## AWS lab protections
- dedicated account if practical
- explicit account allowlist
- required environment variable confirming target
- Terraform state separation
- resource tags
- budget alerts
- region allowlist
- teardown scripts
- TTL/expiry tags where practical

## Terraform safety
Potential safeguards:
- require expected account ID
- refuse unknown workspace
- prevent deletion of non-lab resources
- use synthetic names/prefixes
- document expected cost before apply

## Kubernetes
Prefer local cluster for early RBAC labs where possible.

Use cloud EKS only when cloud identity integration is being tested.

## CI
Avoid deploying paid cloud infrastructure on every PR.

Use:
- mocks
- local containers
- local Kubernetes
- scheduled/manual cloud tests

## Secret management
Local:
- `.env.example`
- environment variables
- local secret storage

CI:
- repository/environment secrets with minimal privilege

Cloud:
- short-lived federation preferred

## Data
Use synthetic:
- users
- agents
- credentials
- secrets
- business metadata

## Cleanup acceptance
A cloud lab is incomplete unless it includes:
- destroy command
- residual-resource check
- cost note
