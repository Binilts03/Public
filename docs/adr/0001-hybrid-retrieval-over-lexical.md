# ADR-0001: Enriched hybrid retrieval (Arm B) over lexical baseline (Arm A)

**Date**: 2026-10-01
**Status**: accepted
**Deciders**: benchmark pilot (evidence: `evals/retrieval_eval.json`, commit `f672df9`)

## Context

Lexical search over sparse tool docs returns zero-overlap queries in corpus order, surfacing high-risk tools for benign queries (measured: `invoice` -> 10/10 high-risk, both harnesses). Tool-REX research predicts enriched metadata plus tool-specific retrieval fixes most of this.

## Decision

We use Tool-REX nested-field extraction (when_to_use 0->898/1000, tags 100->998/1000) plus MiniLM hybrid scoring (0.7 cosine + 0.3 lexical) minus risk penalty (0.45 destructive / 0.15 write) as the discovery path. Lexical `search_tools` stays as the Arm A comparison control.

## Alternatives Considered

### Alternative 1: Lexical only
- **Pros**: No model download, instant cold start
- **Cons**: 0.49 R@1 on use-case queries; 37-49% risky-exposure rate
- **Why not**: Measured worse on both axes that matter

### Alternative 2: Trained tool-retriever (Tool-Embed)
- **Pros**: Best published numbers (+10 N@10 over MTEB SOTA)
- **Cons**: Training cost, maturity risk for a pilot
- **Why not**: Revisit if MiniLM proves insufficient; MiniLM already clears the retrieval gate

## Consequences

### Positive
- Use-query R@1 0.49 -> 0.95; risky exposure down ~80%
- Local, reproducible, no API spend

### Negative
- ~90MB model download; ~12s server cold start; 1.5MB embeds artifact
- Verbatim-query R@1 -2pp (risk penalty occasionally demotes gold writes)

### Risks
- MiniLM scores carry no signal on very short queries (see ADR-0002)
