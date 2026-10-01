# ADR-0003: Adopt compact result contracts with lossless handles (Arm D)

**Date**: 2026-10-01
**Status**: accepted
**Deciders**: benchmark pilot (evidence: `evals/result_auc.json`, commit `f22bf9b`)

## Context

Result payloads dominate long-horizon context: a 200-row search result is ~56KB (~14k tokens) inline. The handoff hypothesized result-debt may matter more than schema-debt. Current MCP (`structuredContent`, resource links) can express bounded views plus addressable full data with no protocol change.

## Decision

External capability results return a bounded deterministic projection (top-3 items, 200-char snippets) plus a `result_handle` resolving to full rows via `get_full_result`. No LLM summarization in the projection path. Measured on a scripted 25-step trajectory: -56.6% cumulative model-visible tokens with 8/8 lossless checks (digest match, exact prefixes).

## Alternatives Considered

### Alternative 1: Full results inline
- **Pros**: Nothing to lose, no plumbing
- **Cons**: 120k vs 52k tokens over 25 steps in measurement
- **Why not**: Measured worse where it counts

### Alternative 2: LLM-summarized results
- **Pros**: Smaller still
- **Cons**: Probabilistic information loss before need is demonstrated
- **Why not**: Rejected until deterministic projection proves insufficient

## Consequences

### Positive
- Clears the provisional >=30% bar at contract level; zero discoverability failures in checks
- Composable with any retrieval arm

### Negative
- Handle lifecycle (expiry, auth per fetch) unimplemented in pilot store
- End-to-end long-horizon success gain (>=5pp) still unmeasured — needs real trajectories

### Risks
- A compact view that hides decisive rows fails even if bytes are retrievable; needs per-task loss audits as tasks widen
