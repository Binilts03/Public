# External Capability Substrate — A/B/C/D Falsification Benchmark

Locked scope: OpenCode + Claude API first, ~1k corpus, new repo.

North-star: can one substrate give harnesses large-universe access with materially less burden/pollution than modern MCP gateway + native deferred Tool Search, preserving real typed tools and native permissions? If A/B ≈ C/D after fair eval: stop, use modern MCP + Tool Search.

Arms:
- A: one MCP gateway + native deferred search + ordinary results
- B: A + enriched metadata + specialized retrieval/rerank, still demand-loaded
- C: B + high-confidence 0–N prefetch + native fallback, abstention allowed
- D: C + bounded deterministic projection + lossless ref

See `corpus/`, `tasks/`, `harness/`, `evals/`. Decisions in `docs/adr/`.

History preserved: prior skill-discovery proposal cleared in commit `9af998d`, not rewritten.
