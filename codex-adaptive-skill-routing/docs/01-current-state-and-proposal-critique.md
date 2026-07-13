# 01 — Current State and Critique of the Original Proposal

## Baselines reviewed

### User proposal

- File: [`deferred-skill-discovery-proposal.md`](https://github.com/Binilts03/Public/blob/main/deferred-skill-discovery-proposal.md)
- Blob reviewed: `29e5e9bdf2e1755c80b326ca8aa34acb6efb3434`
- Date in document: 12 July 2026
- Codex source baseline cited by that document: `9e552e9d15ba52bed7077d5357f3e18e330f8f38`

### Current Codex source baseline

- Repository: [`openai/codex`](https://github.com/openai/codex)
- Commit reviewed: [`8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66`](https://github.com/openai/codex/commit/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66)
- Date reviewed: 13 July 2026

The current baseline is eleven commits ahead of the proposal's source baseline. Those commits include
the new shadow skill-selection work, so the original proposal's “proposed experiment” partially
describes functionality that is already in `main`.

## Verified current behavior

### Public contract

The official Codex documentation states that:

- Codex initially exposes each skill's name, description, and path.
- The initial list is limited to 2% of the context window, or 8,000 characters when context size is
  unknown.
- Descriptions are shortened first and entries may then be omitted.
- The full `SKILL.md` is loaded when Codex chooses a skill.
- Explicit invocation uses a skill mention; implicit invocation matches the task to the skill
  description.

Primary source:
[Build skills](https://developers.openai.com/codex/skills).

### Host inventory and freshness

`SkillsService` already owns:

- discovery from effective roots;
- product filtering;
- configuration-aware enablement;
- immutable `HostSkillsSnapshot` values;
- caches keyed by working directory and effective skill configuration;
- explicit cache invalidation.

`SkillsWatcher` watches applicable local roots, throttles changes, clears the service cache, and
emits a `SkillsChanged` notification. Remote environment roots are intentionally not watched.

Relevant source:

- [`core-skills/src/service.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/core-skills/src/service.rs)
- [`app-server/src/skills_watcher.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/app-server/src/skills_watcher.rs)

### Multiple authority types

The skills extension models:

- host skills;
- selected-executor skills;
- orchestrator-owned skills;
- future custom authorities.

A `SkillCatalogEntry` is bound to an authority, package, main resource, and source-specific read
path. The provider contract requires list/read/search operations to preserve that authority.

Relevant source:

- [`ext/skills/src/catalog.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/catalog.rs)
- [`ext/skills/src/provider.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/provider.rs)

### Two model-visible rendering paths

At the pinned baseline, Codex has parallel behavior:

1. The mature core renderer:
   - 2% token budget or 8,000-character fallback;
   - path aliases;
   - scope ordering;
   - fair description shortening;
   - omission reporting and metrics.

2. The skills-extension renderer:
   - fixed 8,000 UTF-8 byte cap;
   - per-description cap;
   - iteration-order omission;
   - a separate 8,000-byte selected-main-prompt cap.

This is not merely an implementation detail. A final solution that edits only one renderer can
leave another runtime path lossy or inconsistent.

Relevant source:

- [`core-skills/src/render.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/core-skills/src/render.rs)
- [`ext/skills/src/render.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/render.rs)

### Explicit invocation

The host already resolves explicit structured selections and textual skill mentions against the
enabled inventory. Explicitly selected instructions are read before model execution. This path does
not depend on the bounded implicit catalogue.

### Newly merged shadow selector

PRs
[#32761](https://github.com/openai/codex/pull/32761),
[#32768](https://github.com/openai/codex/pull/32768), and
[#32780](https://github.com/openai/codex/pull/32780) added and enabled:

- `CheapSkillSelector`;
- `WeightedLexicalSkillSelector`;
- a bounded query/document implementation;
- deterministic tie-breaking;
- a shadow experiment that ranks prompt-visible metadata;
- metrics for latency, reduction, and whether a later observed invocation appears in the ranking.

The selection is deliberately not yet model-visible.

### Current shadow-evaluation limitation

The shadow experiment only measures host and orchestrator entries because current structured
observation exists for host shell usage and orchestrator `skills.read`. Executor entries were
removed from the experiment to avoid skewing the metric. This is an observability limitation, not a
valid production reason to exclude executor skills from adaptive routing.

The host “implicit invocation” signal is itself an approximation: it observes the model reading a
known `SKILL.md` or running a script under a skill's `scripts` directory. It does not prove that
every correct or incorrect selection was observed.

## What the original proposal got right

The original proposal correctly established that:

- the complete host inventory already exists outside model context;
- another filesystem scanner or persistent database is unnecessary;
- explicit invocation should remain unchanged;
- catalogue discovery and package-internal resource search are different operations;
- result count and result bytes must be bounded;
- lexical ranking is the appropriate first local selector;
- search must not execute skill content;
- raw directory counts are weaker evidence than effective-catalogue metrics;
- prompt caching does not make context occupancy disappear.

Those conclusions are retained.

## Why the original proposal is not correct as the build direction

### 1. Its upstream baseline is stale

The proposal asks whether catalogue search is planned and proposes adding the first lexical
experiment. The next day's upstream source already contains a default-enabled lexical shadow
experiment.

A coding assistant following the proposal literally would duplicate or conflict with:

- `dynamic_skill_selector`;
- `WeightedLexicalSkillSelector`;
- `ShadowSelectionExperiment`;
- existing metrics and feature wiring.

### 2. It treats omission as the only definite trigger

The proposal says retrieval should run only when `omitted_count > 0` and that shortening should wait
for further evidence.

That boundary is too narrow for the completed solution. Implicit matching depends on the description,
and the official documentation warns authors that descriptions may be shortened. Removing scope,
negative boundaries, named artifacts, or trigger words can change routing even while the skill name
remains visible.

The final trigger is:

```text
lossy = truncated_description_chars > 0 OR omitted_count > 0
```

### 3. It searches only the host snapshot

The proposal's operation searches `HostSkillsSnapshot`. Current Codex has separate host, executor,
and orchestrator catalogues and explicitly models future custom sources.

A host-only implementation would:

- miss selected-environment skills;
- miss hosted/orchestrator skills;
- create different semantics across clients and environments;
- fail to bind search results to the provider that must read them.

The final solution searches the complete effective per-step snapshot.

### 4. It leaves parallel catalogue owners unresolved

The proposal assumes one renderer/report boundary. Current source has distinct core and extension
renderers and separate host/executor/orchestrator projection paths.

The final solution requires one authoritative model-visible catalogue per model step.

### 5. It frames automatic and model-triggered search as competing alternatives

They solve different failure modes:

- automatic selection avoids a discovery round trip for the common case;
- model-triggered search recovers from weak wording, multilingual mismatch, referential requests,
  mixed tasks, and facts learned after file inspection.

The complete solution requires both.

### 6. It does not specify “skills as rules”

The proposal treats search primarily as term matching. It does not define how trusted runtime
signals—URL type, attachment MIME, file extension, review mode, provider identity, declared tool
dependency, repository scope, or previous task continuity—should affect ranking.

The final solution compiles those facts into bounded routing evidence. It does not add a mandatory
global category registry.

### 7. It does not define explicit multi-skill behavior

It does not resolve:

- user ordering;
- duplicate references;
- one missing or disabled skill;
- ambiguous names;
- implicit supplementation;
- conflicting instructions;
- combined body size;
- dependency readiness;
- source replacement between steps.

These semantics are normative in this document set.

### 8. It assumes selected instructions can simply be loaded

At the current skills-extension path, selected main prompts may be silently truncated to 8,000 bytes.
A final implementation cannot claim to follow complete skill instructions while injecting only an
unmarked prefix.

The final direction provides bounded inline instructions and paginated authority-preserving reads,
with no silent body truncation.

### 9. It does not provide a per-step freshness contract

A running turn may observe:

- a newly ready executor;
- a reconnected environment;
- a plugin or host snapshot refresh;
- an orchestrator MCP generation change.

The final design binds candidate metadata and subsequent reads to the same immutable model-step
snapshot.

### 10. It leaves search tool ownership and state underspecified

The current `SkillProvider::search` shape is package-oriented and all current providers return empty
results. The model-visible `skills` namespace currently lists and reads orchestrator skills only.
A complete implementation needs a distinct catalogue-search contract and a uniform deferred read
contract.

### 11. It lacks complete failure, security, and compatibility contracts

The proposal contains good guardrails but not enough for implementation. It does not prescribe hard
behavior for stale handles, oversized catalogues, malicious descriptions, concurrent refresh,
resume/fork, compaction, source disappearance, tool output accumulation, malformed UTF-8 boundaries,
or failed dependency startup.

### 12. Its rollout language is not suitable for this coding issue

The original document is correctly cautious as a product proposal, but “offer an opt-in recovery
path” and “keeping current behavior is a valid outcome” are not the requested engineering target.

For this work:

- shadow comparison is mandatory verification;
- reviewable commits are allowed;
- the final state must be fully functional;
- no partial “MVP” is considered complete.

## Prior art that must not be misrepresented

### PR #27804 — model-visible `skill_search`

This draft proposed replacing the static catalogue with a BM25-backed `skill_search` tool. It was
closed automatically after inactivity, not rejected on technical merits. Its turn-scoped tool-state
work and result limits are useful prior art, but tool-only discovery is not selected as the complete
solution.

### PRs #29943, #29960, and #29965 — unified runtime snapshots

These unmerged stacked changes explored:

- source-neutral rendering;
- one per-step skills snapshot;
- authority-bound reads;
- executor availability projection;
- unified selection;
- selected-body caps.

They are not current behavior. Their invariants are valuable, especially the requirement that the
catalogue shown to the model and the source used to read a skill come from the same snapshot.

## Corrected problem statement

> Codex owns a complete, filtered, authority-bound skill inventory outside model context, but
> implicit skill discovery still relies on model-visible metadata rendered through multiple bounded
> paths. At scale, those paths shorten descriptions or omit entries. A newly merged lexical shadow
> selector demonstrates a local ranking seam, but it does not yet control context, cover all
> authorities, use trusted task evidence, support recovery, or provide uniform complete reads.
> Codex needs one per-step skill snapshot and an adaptive routing path that preserves exact explicit
> behavior, keeps lossless small catalogues unchanged, replaces lossy large catalogues with a bounded
> relevant subset, and lets the model recover omitted candidates without violating authority,
> freshness, security, or context limits.

That is the issue this package specifies.
