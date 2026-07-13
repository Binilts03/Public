# Unified Adaptive Skill Routing for Codex

This directory is a reviewable patch project for `openai/codex`, based on commit
`c7a4a7e136d96554e1fc6f66532e6060fd2aaf15` (2026-07-13). It turns Codex's
existing shadow lexical selector into loss-aware, authority-neutral routing while
preserving deterministic explicit invocation.

This is a coding change, not a SaaS proposal and not an MVP. The feature is
complete behind the under-development `adaptive_skill_routing` flag so Codex
maintainers can run the required shadow and regression gates before changing the
default.

## Why the original proposal is not the implementation plan

[`deferred-skill-discovery-proposal.md`](../deferred-skill-discovery-proposal.md)
correctly identifies bounded model-visible metadata, but its build direction is
stale and incomplete:

- it activates only on omission, although description shortening is already a
  loss of routing evidence;
- it frames lexical retrieval as new even though upstream already contains a
  default-enabled weighted lexical shadow selector and metrics;
- it is host-centric while current Codex has host, executor, orchestrator, and
  custom authorities;
- it does not eliminate competing core, thread, world-state, and turn catalogue
  injection paths;
- it treats automatic candidates and model-requested recovery as alternatives,
  though they cover different misses;
- it leaves multi-skill atomicity, stale handles, pagination, oversized skill
  bodies, multilingual/typo matching, lifecycle changes, and recovery limits
  underspecified.

The corrected problem is narrower and testable:

> Codex already owns the complete effective skill inventory and resolves explicit
> invocations. Implicit routing is lossy when its model-visible catalogue shortens
> or omits metadata. Replace only that lossy presentation with a turn-scoped
> shortlist over the same immutable snapshot, and make retrieval misses
> recoverable without exposing the complete catalogue.

## Implemented behavior

- one shared budget-aware renderer for every authority;
- full catalogue retained when it fits without shortening or omission;
- adaptive shortlist only when rendering would be lossy;
- task evidence from name, descriptions, source, package, locator, scope, plugin,
  dependencies, attachments, and bounded turn continuity;
- deterministic lexical, typo, and unsegmented-CJK matching with a 10,000-entry
  hard bound;
- exact, ordered, all-or-none explicit multi-skill loading;
- one authoritative app-server catalogue, with legacy core fallback when the
  extension is absent;
- `skills.search`: two calls, eight results per call, sixteen unique recovery
  candidates, 8 KiB response metadata, initial-candidate suppression;
- authority-bound `skills.list` and `skills.read` over the exact turn snapshot;
- UTF-8-safe 8 KiB read pages and a cumulative 1 MiB explicit-instruction bound;
- stale turn handles fail closed; there is no "latest snapshot" fallback;
- an under-development feature flag, trace events, and focused regression tests.

## Patch series

1. `0001` — shared authority-neutral rendering;
2. `0002` — loss-aware routing, lifecycle, evidence, and explicit semantics;
3. `0003` — bounded recovery search and paginated reads.
4. `0004` — compiler-driven visibility and non-exhaustive protocol fixes.
5. `0005` — require meaningful fuzzy overlap so n-gram recovery does not admit unrelated skills.
6. `0006` — preserve legacy shadow-selection authority scope when adaptive routing is disabled.
7. `0007` — isolate adaptive prompt semantics while retaining legacy explicit executor and hidden-skill behavior.

Apply the patches to the pinned Codex baseline:

```bash
git clone https://github.com/openai/codex.git
cd codex
git checkout c7a4a7e136d96554e1fc6f66532e6060fd2aaf15
git am ../Public/codex-adaptive-skill-routing/patches/*.patch
```

Run `../Public/codex-adaptive-skill-routing/scripts/verify.sh` from the Codex
checkout, or run the included GitHub Actions workflow.

## Documentation authority

Read in this order:

1. [`AGENTS.md`](AGENTS.md) — coding-assistant execution contract;
2. [`IMPLEMENTATION-STATUS.md`](IMPLEMENTATION-STATUS.md) — code/evidence status;
3. [`docs/00-engineering-decision.md`](docs/00-engineering-decision.md);
4. [`docs/01-current-state-and-proposal-critique.md`](docs/01-current-state-and-proposal-critique.md);
5. the remaining numbered documents in [`docs`](docs).

The numbered engineering documents are normative where they describe behavior.
When a document's pinned source snapshot differs from the baseline above, the
baseline and patch series in this README control.
