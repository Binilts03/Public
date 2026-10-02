# ADR-0007: Single-harness focus on OpenCode until native baselines unblock

**Date**: 2026-10-01
**Status**: accepted
**Deciders**: scope direction (human) + benchmark pilot

## Context

Cross-harness CI across Codex/Claude/OpenCode was the original plan. Reality: Codex needs an experimental App Server client, Claude Code needs login/key for native numbers, and Ollama-backed Claude runs test harness mechanics only (ADR-0004). Splitting thin live effort across three harnesses dilutes the one environment where iteration is free and fully instrumented.

## Decision

Skip Claude and Codex for now. All live work runs on OpenCode (cost 0, full JSON traces, working MCP plumbing). Claude/Codex return when either native credentials exist (real Tool Search baselines) or a provider-injected seam exists to test (H7). Offline contract evals (retrieval, frontier, AUC) stay harness-agnostic and transferable.

## Alternatives Considered

### Alternative 1: Keep spending on Ollama-backed Claude runs
- **Pros**: Cross-harness existence proofs
- **Cons**: ~$0.15-0.57 per run for behavior that does not transfer to Claude-model numbers; LH2 showed permission-shy dithering specific to the open model
- **Why not**: Cost without falsification value at this stage

### Alternative 2: Build the Codex App Server client now
- **Pros**: Third harness
- **Cons**: Experimental API, custom client, same open-model limitation at the end
- **Why not**: Premature; H7 seam needs vendor stability first

## Consequences

### Positive
- All live effort compounds in one instrumented environment; prior Claude findings stay valid as labeled case evidence
- Cloud spend drops to zero for live work

### Negative
- No new cross-harness data until unblocked; H7 untouched

### Risks
- OpenCode-specific behavior (e.g., 40k eager baseline) may not generalize; label accordingly
