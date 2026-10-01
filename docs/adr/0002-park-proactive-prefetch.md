# ADR-0002: Park proactive prefetch (Arm C equals Arm B with cheap retrieval)

**Date**: 2026-10-01
**Status**: accepted
**Deciders**: benchmark pilot (evidence: `evals/prefetch_frontier.json`, commit `7497e1d`)

## Context

The prefetch gate calibrated at tau=0.65 looked strong on known-item queries (0.90 coverage, 0.00 negative-emit). On the 10 realistic short prompts it abstained 10/10: positives score 0.17-0.41, must-abstains score 0.24-0.42. No threshold separates them.

## Decision

Park the cheap-prefetch variant (MiniLM + threshold on turn text only). Ship the `prefetch` tool with its hard rules (destructive never, budget-gated writes) but do not claim any working-set advantage: measured C identical to B. Revisit only with a stronger retriever, entity-aware trusted state (H3), or longer contexts — never by adding another agent to fix routing.

## Alternatives Considered

### Alternative 1: Lower tau to buy coverage
- **Pros**: Prefetch fires on real queries
- **Cons**: Negative-emit 5-40%; prefetches on no-tool tasks at similar rates
- **Why not**: Violates the precision-first operating point the hypothesis requires

### Alternative 2: LLM rerank/decision model now (H5)
- **Pros**: Might restore separation
- **Cons**: Latency, cost, complexity before retrieval debt is paid
- **Why not**: H5 survives only if it moves the frontier; untested, so parked with C

## Consequences

### Positive
- No false-prefetch machinery taxing context and trust
- Falsification recorded as evidence, not opinion

### Negative
- H1/H2 unproven for short turns; long-horizon prefetch value unknown

### Risks
- Revisit needs paired evidence, not enthusiasm
