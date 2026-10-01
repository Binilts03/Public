# ADR-0004: Harness-only testing via Ollama-backed harnesses, labeled

**Date**: 2026-10-01
**Status**: accepted
**Deciders**: benchmark pilot

## Context

No Anthropic key and no Claude login existed, but both harnesses were testable: `ollama launch claude` runs Claude Code 2.1.281 on `gpt-oss:20b-cloud` (verified via `modelUsage`), and `ollama launch opencode` runs OpenCode 1.18.34 the same way. This tests harness mechanics, not provider models.

## Decision

All live-run evidence is labeled harness-plus-open-model behavior. It covers tool loops, permission UX, MCP plumbing, refusal paths, and trace shape. It never stands in for Anthropic/OpenAI native Tool Search numbers (server variants, reference expansion, cache rules), which stay blocked on key/login. The `[claude-code:unrecognized_model]` stderr warning is non-fatal and recorded.

## Alternatives Considered

### Alternative 1: Wait for keys before any live runs
- **Pros**: No labeling burden
- **Cons**: Blocks all harness-integration learning
- **Why not**: Harness mechanics decoupled cleanly from provider behavior

### Alternative 2: Present Ollama-backed runs as baselines
- **Pros**: None honest
- **Cons**: Invalidates A/B comparisons
- **Why not**: Rejected explicitly

## Consequences

### Positive
- Gate-0, smoke, and refusal evidence without API spend (~$0.40 total so far)

### Negative
- Every live-run claim needs the harness-only qualifier until native runs reproduce it

### Risks
- Open-model behavior (e.g., Grep-instead-of-gateway miss) may not transfer to frontier models; treat as existence proofs, not rates
