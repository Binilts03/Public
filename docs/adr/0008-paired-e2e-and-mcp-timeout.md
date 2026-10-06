# ADR-0008: Paired A/B end-to-end result and MCP cold-start timeout fix

**Date**: 2026-10-06
**Status**: accepted
**Deciders**: benchmark pilot (evidence: `evals/e2e_grades.json`, `evals/e2e_traces/` ignored, commit pending)

## Context

The decision memo left paired A/B end-to-end task-success deltas unmeasured.
`evals/e2e_paired.py` gates live runs behind `--execute + OPENCODE_E2E_LIVE=1`
plus explicit human go-ahead. First live 50-run attempt returned
A 0.40 / B 0.40 with zero `gateway_*` calls in every trace: a null run,
not a tie. `opencode mcp list` showed `gateway failed — Operation timed
out after 30000ms`. Measured cold start of `all-MiniLM-L6-v2` is ~45s
online / ~27s with `HF_HUB_OFFLINE=1`, over the MCP default 5s (30s
effective) fetch timeout.

## Decision

1. Fix harness only: `harness/opencode/pilot/opencode.json` gateway entry
   gains `"timeout": 120000` and `"environment":
   {"HF_HUB_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"}`.
   No substrate change. Verified `opencode mcp list → gateway connected`
   and single live probe shows `gateway_search_tools` called.
2. Re-ran valid paired E2E (25 tasks x A/B, `gpt-oss:20b-cloud`,
   harness-only per ADR-0004): **A 0.64 (16/25) vs B 0.56 (14/25),
   delta_B_minus_A = -0.08**. Consult A 6/25, B 7/25 (gold expects 15).
   Divergent: A takes T01/T03/T08/T16/T18, B takes T12/T22/T23.
3. Safety: 0 destructive executes. Sole execute in 50 runs is
   B-T16 `call_compact(cap_0459, "?")` → `invalid_arguments_json`,
   rejected, no effect. Unavailable correctly reported via
   `unavailable: [cap_unavail_*]`.
4. Interpretation: B's offline retrieval win (R@1 0.50→0.93, exposure
   0.49→0.08) does not translate to task-success gain on this
   open-model harness; bottleneck is model initiative (never consulting),
   not ranking. n=25, noisy. B+D stay adopted per retrieval/contract
   evidence; E2E does not overturn them. Next E2E needs forced-consult
   variant (cf. T11_retry success) or frontier-model harness.

## Alternatives Considered

### Alternative 1: Cite 0.40/0.40 null as tie
- **Pros**: None honest
- **Cons**: Zero gateway calls in all traces; measures plumbing failure
- **Why not**: Discarded explicitly; traces preserved as null evidence

### Alternative 2: Lazy-load model in gateway server
- **Pros**: Fast MCP list_tools without env/timeout config
- **Cons**: Windows FastMCP worker-thread deadlock risk (see server
  comment); larger change than config fix
- **Why not**: Revisit only if 120s timeout proves flaky

## Consequences

### Positive
- First valid paired E2E fills the decision-memo gap (harness-only scope)
- Cold-start trap documented; future harnesses set timeout+offline env

### Negative
- `evals/e2e_traces/` (50 files, ~284KB) ignored as artifacts, like
  `gateway_calls.jsonl`; only `evals/e2e_grades.json` committed
- open-model initiative gap remains the E2E bottleneck

### Risks
- Temp-path absolute config is machine-specific (pre-existing); portable
  pilot config still open
