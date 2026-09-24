# Architecture Decision Records

Use ADRs for decisions that:
- materially affect architecture
- change security assumptions
- create long-term coupling
- replace major infrastructure
- alter public contracts
- are likely to be revisited

## Naming
```text
0001-short-title.md
0002-short-title.md
...
```

## Status values
- Proposed
- Accepted
- Superseded
- Rejected
- Deprecated

## Register

- [ADR-0001: Persistence ownership and snapshot projection](0001-persistence-and-snapshot-projection.md) — Accepted
- [ADR-0002: Compare complete retained inventory observations](0002-observed-inventory-comparison.md) — Accepted

## Expected next ADRs

- normalized identity and provenance model
- graph relationship semantics and edge evidence (the first node projection is covered by
  ADR-0001)
- policy engine integration and policy precedence
- runtime gateway deployment and failure model
- delegation representation and validation
