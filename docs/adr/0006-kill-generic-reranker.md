# ADR-0006: Kill generic-reranker H5 variant; long-horizon split decision

**Date**: 2026-10-01
**Status**: accepted
**Deciders**: benchmark pilot (evidence: `evals/rerank_eval.json`, `evals/lh1_opencode.jsonl`, `evals/lh2_claude.json`)

## Context

H5 asked whether a dedicated decision stage moves the risk-coverage frontier. Tested: CrossEncoder ms-marco-MiniLM-L6-v2 over v2 top-20 plus the same risk penalty, 100 use-queries.

## Decision

Kill the generic-reranker H5 variant. Measured: R@1 0.94 -> 0.88 (worse), R@3 0.96 -> 0.98 (noise), exposure 0.08 -> 0.09 (flat), +47ms p50. A general-purpose IR reranker does not transfer to tool ranking — directly reproducing the ToolRet literature finding. The only surviving H5 variant is a tool-trained ranker (Tool-Rank recipe), untested.

## Alternatives Considered

### Alternative 1: Adopt rerank for R@3 +0.02
- **Pros**: Tiny top-3 gain
- **Cons**: R@1 regression where precision matters most, extra dependency
- **Why not**: Fails the pre-registered bar (>=10pp coverage or halved risk)

### Alternative 2: Bigger generic reranker
- **Pros**: Might recover R@1
- **Cons**: Same transfer problem, larger; literature says the gap is domain, not size
- **Why not**: Wrong direction per ToolRet/Tool-REX evidence

## Consequences

### Positive
- One fewer inference dependency; threshold gate stands

### Negative
- H5 alive only via tool-specific training (data + compute cost unestimated)

### Risks
- None for the pilot; the killed variant stays dead unless a tool-trained ranker is evaluated

## Long-horizon case notes (same session, n=1 each, existence evidence only)

- LH1 OpenCode: SUCCESS — 5-step chain (search, details, compact call, search, summary), 4 gateway calls, cost 0.
- LH2 Claude/open-model: FAILURE — 11 turns, 0 gateway calls, ended asking permission ($0.57). Same --allowedTools shape that worked for single searches; permission-shy dithering under multi-step instruction is model/harness behavior, not gateway behavior.
