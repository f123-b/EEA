# M2 Next Phase

## Target

M3 EngineeringValue + Claim Core, including V1.3.1 FIX-02 Canonical Unit foundation.

## Scope

- the single Core `EngineeringValue` contract
- frozen engineering dimensions and canonical units
- `UnitNormalizationService`; rules and comparisons consume normalized values only
- `EngineeringClaim`, ClaimConflict, ClaimResolver, and ClaimPredicateRegistry
- source priority, applicability, lifecycle, and verification levels
- Evidence-gated `DOCUMENT_VERIFIED` behavior
- deterministic Errata, package, and revision conflict tests
- FIX-02 acceptance: 24 V = 24000 mV, 48 V > 40 V, 1 kHz = 1000 Hz,
  1000 us = 1 ms, and cross-dimension comparisons fail

## Dependencies

- accepted M1 Core entities, Evidence, schema registry, and engineering errors
- accepted M2 StructuredGeneration foundation; M3 deterministic Claim resolution must not depend on
  model judgment
- V1.3.1 FIX-02 final EngineeringValue contract and dimension catalog

## Sequencing

FIX-02 is implemented with M3 and must pass before M7/M9 rules compare engineering values. FIX-03
and later corrections remain at their documented insertion points.

## Blockers

None. Unit conversion should use one vetted conversion backend behind the Core normalization service;
no Pin, electrical-rule, or multi-agent scope is pulled into M3.
