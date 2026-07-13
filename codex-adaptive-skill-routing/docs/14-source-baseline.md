# 14 — Source Baseline and Evidence

## Baseline rule

All source claims in this package were checked against:

- `openai/codex` commit [`8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66`](https://github.com/openai/codex/commit/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66);
- public OpenAI documentation available on 13 July 2026;
- Agent Skills specification available on 13 July 2026;
- the user's proposal blob `29e5e9bdf2e1755c80b326ca8aa34acb6efb3434`.

Implementation must re-check current `main` before editing.

## Primary public documentation

### Codex skills

[Build skills](https://developers.openai.com/codex/skills)

Supports:

- progressive disclosure;
- initial name/description/path;
- 2% context or 8,000-character fallback;
- description shortening and possible omission;
- complete selected `SKILL.md` read;
- explicit and implicit invocation;
- implicit reliance on description;
- automatic skill-change detection;
- repository/user/admin/system locations;
- duplicate names not merged.

### Agent Skills specification

[Agent Skills specification](https://agentskills.io/specification)

Supports:

- required `name`;
- required `description`;
- description must state what and when;
- keyword guidance;
- 1,024-character description maximum;
- optional arbitrary metadata;
- full body loaded after activation;
- recommendation to split long content into references.

This package does not require a new mandatory metadata field even though the standard permits
additional metadata.

### Tool search

[Tool search](https://developers.openai.com/api/docs/guides/tools-tool-search)

Supports the architectural analogy that:

- definitions can be deferred;
- client-executed search is appropriate when availability depends on application/project state;
- the client controls search;
- returned definitions must be validated;
- dynamically loaded definitions can be appended later.

Tool search is not proof that skills already use the same protocol.

### Prompt caching

[Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)

Supports:

- exact-prefix matching;
- static content before variable content;
- cache reuse reduces processing cost/latency;
- caching does not remove logical prompt content.

## Current Codex implementation sources

### Inventory, metadata, and lifecycle

- [`core-skills/src/model.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/core-skills/src/model.rs)
- [`core-skills/src/loader.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/core-skills/src/loader.rs)
- [`core-skills/src/service.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/core-skills/src/service.rs)
- [`app-server/src/skills_watcher.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/app-server/src/skills_watcher.rs)

Key facts:

- `SkillMetadata` retains scope and plugin ID.
- `HostSkillsSnapshot` is immutable and retains filesystem mapping.
- `SkillsService` owns caches and filtering.
- watcher invalidates host cache.
- `allow_implicit_invocation` is separate from enabled state.

### Renderers

- [`core-skills/src/render.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/core-skills/src/render.rs)
- [`ext/skills/src/render.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/render.rs)

Key fact: parallel renderers differ in budget/allocation behavior.

### Extension/catalogue/provider

- [`ext/skills/src/catalog.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/catalog.rs)
- [`ext/skills/src/provider.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/provider.rs)
- [`ext/skills/src/provider/host.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/provider/host.rs)
- [`ext/skills/src/provider/executor.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/provider/executor.rs)
- [`ext/skills/src/provider/orchestrator.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/provider/orchestrator.rs)
- [`ext/skills/src/extension.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/extension.rs)
- [`ext/skills/src/state.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/state.rs)

Key facts:

- Host, executor, orchestrator, custom authority kinds.
- Providers own list/read boundaries.
- provider `search` is package-shaped and currently empty.
- host mapping drops some routing metadata into neutral catalogue.
- current turn code runs shadow ranking but still renders old context.
- executor catalogue can be projected separately through world state.

### Model-visible tools

- [`ext/skills/src/tools/mod.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/tools/mod.rs)
- [`ext/skills/src/tools/list.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/tools/list.rs)
- [`ext/skills/src/tools/read.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/tools/read.rs)

Key facts:

- current namespace registers `list` and `read`;
- current authority enum is orchestrator-only;
- tools are registered based on orchestrator availability;
- current `ToolContributor` receives session/thread state, not turn state.

### Shadow selector

- [`ext/skills/src/dynamic_skill_selector.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/dynamic_skill_selector.rs)
- [`ext/skills/src/dynamic_skill_selector/weighted_lexical.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/dynamic_skill_selector/weighted_lexical.rs)
- [`ext/skills/src/shadow_selection_experiment.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/src/shadow_selection_experiment.rs)
- [`ext/skills/tests/implicit_invocation.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/ext/skills/tests/implicit_invocation.rs)

Key facts:

- deterministic bounded weighted lexical selection;
- current user input only;
- max 20 shadow results;
- host/orchestrator observability;
- selection not model-visible;
- temporary experiment comment.

### Feature state

- [`features/src/lib.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/features/src/lib.rs)
- [`app-server/src/extensions.rs`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/codex-rs/app-server/src/extensions.rs)

`skill_search` is stable and default-enabled, but currently enables shadow metrics rather than active
candidate context.

### Repository contribution requirements

- [`AGENTS.md`](https://github.com/openai/codex/blob/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66/AGENTS.md)

Relevant requirements:

- use `just`, not direct `cargo test`;
- model-visible context bounded;
- no history rewrite;
- avoid frequent cache-breaking context changes;
- no item larger than 10K tokens;
- agent changes require integration tests;
- complex changes should be split for review;
- avoid growing `codex-core`;
- update config/Bazel lockfiles where applicable.

## Merged upstream changes after the original proposal baseline

### PR #32761

[Add shadow metrics for lexical skill selection](https://github.com/openai/codex/pull/32761)

Merged:

- selector abstraction;
- weighted lexical ranker;
- shadow experiment;
- metrics;
- tests.

### PR #32768

[Align shadow skill selection with observable sources](https://github.com/openai/codex/pull/32768)

Merged:

- restrict experiment to host/orchestrator because only those invocations were observable.

This does not establish a production exclusion for executor skills.

### PR #32780

[Enable skill search shadow selection by default](https://github.com/openai/codex/pull/32780)

Merged:

- stable/default feature state for collecting shadow metrics.

## User-reported issue evidence

### Issue #24299

[Hard budget and mass description truncation](https://github.com/openai/codex/issues/24299)

Reported:

- 119 skills;
- 103 descriptions truncated;
- 5,440-character budget in that environment.

Treat this as a user report, not fleet-wide prevalence.

### Issue #19090

[Desktop app deterministically omits repo-local skills](https://github.com/openai/codex/issues/19090)

Reported:

- 60 repository plus 5 system skills;
- same trailing set absent from model-visible prompt;
- implicit routing impact.

Treat as a reproducible user report, not proof of all clients.

### Issue #21425

[Separate installed plugins from per-session skill metadata injection](https://github.com/openai/codex/issues/21425)

Shows user demand to keep capabilities installed without always paying full model-visible metadata
cost.

## Unmerged prior art

### PR #27804

[Add skill search tool for dynamic skill discovery](https://github.com/openai/codex/pull/27804)

Draft, closed automatically for inactivity. It proposed:

- model-visible search tool;
- BM25;
- turn-scoped state;
- disabling static catalogue.

Useful prior art; not current behavior and not a technical rejection.

### PR #29943

[Share runtime skill rendering and selection](https://github.com/openai/codex/pull/29943)

Unmerged/folded into another stack. Proposed source-neutral rendering and fair allocation.

### PR #29960

[Cache stable executor skills and project them per model step](https://github.com/openai/codex/pull/29960)

Unmerged. Proposed stable executor metadata cache and per-step projection.

### PR #29965

[Refresh skills for each model step](https://github.com/openai/codex/pull/29965)

Unmerged. Proposed:

- one immutable `SkillsSnapshot`;
- unified source selection/read;
- world-state replacement;
- exact-locator behavior;
- selected-body limits.

Useful architecture precedent; not current behavior.

## Evidence classifications

| Classification | Meaning |
|---|---|
| Documented | Official public contract |
| Implemented | Present at pinned current commit |
| Reported | User issue evidence |
| Prior art | Unmerged design, not current |
| Required design | Normative decision in this package |
| Maintainer verification | Needs upstream telemetry/review |

Every claim in implementation discussions should use one of these classifications.

## What remains inaccessible externally

The following cannot be truthfully answered from public sources:

- fleet-wide truncation/omission frequency;
- fleet-wide shadow top-k recall;
- production false-activation rate;
- internal model-specific routing results;
- maintainer preference for exact PR decomposition;
- internal release/rollout schedule.

This package converts those unknowns into explicit verification gates. It does not fabricate answers.
