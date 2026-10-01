# ADR-0005: Entity-aware retrieval revives prefetch partially, not sufficiently

**Date**: 2026-10-01
**Status**: accepted
**Deciders**: benchmark pilot (evidence: `evals/entity_eval.json`, `search_tools_v3`)

## Context

ADR-0002 parked cheap prefetch after 0/10 coverage. The H3 hypothesis said turn plus trusted operational state (providers, object IDs) might carry enough signal. Tested via deterministic provider bonus (+0.30) and object-ID bonus (+0.10) in `search_tools_v3`, with the prefetch gate rebuilt on top.

## Decision

Entity state moves prefetch from 0/6 to 2/6 coverage at zero false-prefetches (T01/T05 cross tau=0.65; T03/T04/T09/T10 still abstain). Product status of C stays parked — 33% coverage does not justify a working-set seam. The research direction is un-parked specifically for trained tool-retrievers, where the same bonus structure may separate further.

## Alternatives Considered

### Alternative 1: Attested-providers-only bonus
- **Pros**: Purest H3 reading
- **Cons**: Abstained 10/10 including positives — tools are billing-worded while attested state says mail, and the harness cannot know the provider without solving retrieval first (circular)
- **Why not**: Measured dead; bonus must be turn-text computable to fire at all

### Alternative 2: Lower tau to 0.55 for coverage
- **Pros**: 4-5/6 coverage
- **Cons**: T03 native-only (0.57) prefetches external file tools — task-type ambiguity, not ranking error
- **Why not**: Residual overlap is task-type signal no score carries; needs harness-side native-preference policy, out of substrate scope

## Consequences

### Positive
- Prefetch path preserved and calibrated; v3 ranker strictly dominates v2 for entity-bearing turns
- Circular-dependency finding constrains future designs away from attestation-gated retrieval

### Negative
- Two prefetch code paths (bare + state) share scoring by convention, not by construction — refactor to one `_rank` helper before further work

### Risks
- Open-model harness behavior only; frontier models may use the same signals differently
