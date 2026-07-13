# 12 — Complete Implementation Plan

## Principle

The work may be split into reviewable dependent pull requests to comply with Codex review-size
guidance. The complete stack is one solution. There is no MVP completion point.

Pinned starting baseline: `8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66`.

Before editing, rebase/compare against current `main` and map changed upstream files to the same
functional owners.

## Required change stack

## Change 1 — Unify model-visible catalogue primitives

### Objective

Remove rendering/selection divergence without changing active routing yet.

### Work

- Generalize the mature fair renderer to authority-neutral `SkillRenderLine`.
- Add exact UTF-8 byte enforcement.
- Preserve host aliases, report, metrics, warnings, and deterministic order.
- Route extension full-catalogue rendering through the shared primitive.
- Add routing metadata projection (`scope`, `plugin_id`, optional plugin display name) to
  `SkillCatalogEntry`.
- Add identity helpers.
- Prove extension output parity where semantics should match.
- Keep shadow selector behavior unchanged.

### Likely files

```text
codex-rs/core-skills/src/render.rs
codex-rs/core-skills/src/lib.rs
codex-rs/ext/skills/src/catalog.rs
codex-rs/ext/skills/src/provider/host.rs
codex-rs/ext/skills/src/render.rs
codex-rs/ext/skills/tests/skills_extension.rs
```

### Exit criteria

- one shared bounded allocator;
- no context regression;
- existing tests pass;
- multibyte cap tests;
- no new runtime behavior.

## Change 2 — Build authority-bound routing snapshot

### Objective

Create one immutable effective snapshot suitable for rendering, search, and read.

### Work

- Add `routing/snapshot.rs`.
- Bind entries to owner/source generation.
- Add explicit and implicit views.
- Validate duplicate identity, authority/resource, enabled/prompt-visible state.
- Integrate host, executor, orchestrator, and custom catalogues.
- Store active step by exact turn ID in `SkillsThreadState`.
- Add turn lifecycle cleanup.
- Add structured invocation observation for executor/custom reads.
- Do not activate candidate narrowing yet.

### Likely files

```text
codex-rs/ext/skills/src/routing/snapshot.rs
codex-rs/ext/skills/src/routing/snapshot_tests.rs
codex-rs/ext/skills/src/state.rs
codex-rs/ext/skills/src/extension.rs
codex-rs/ext/skills/src/provider/*
codex-rs/ext/extension-api/src/contributors/skill_invocation.rs (only if necessary)
```

### Exit criteria

- every authority listed/read from same snapshot;
- explicit resolution parity;
- lifecycle tests;
- no duplicate catalogue owner.

## Change 3 — Complete task evidence and active selector

### Objective

Promote the existing lexical experiment into a complete policy-assisted selector while still running
in shadow mode.

### Work

- Move/retain current weighted lexical selector under `routing`.
- Add Unicode normalization and robust tokenization.
- Add bounded prior-user context.
- Add URL, MIME, extension, action, concern, dependency, plugin, scope, and continuity evidence.
- Add deterministic fused weights.
- Add abuse resistance.
- Add 10,000-entry cap.
- Add candidate allocator.
- Extend shadow metrics and benchmark corpus.
- Compare `weighted_lexical_v1` and fused selector.

### Likely files

```text
codex-rs/ext/skills/src/routing/evidence.rs
codex-rs/ext/skills/src/routing/selector.rs
codex-rs/ext/skills/src/routing/allocator.rs
codex-rs/ext/skills/src/dynamic_skill_selector/*
codex-rs/ext/skills/src/shadow_selection_experiment.rs
codex-rs/ext/skills/tests/implicit_invocation.rs
```

### Exit criteria

- deterministic tests;
- 200-case benchmark;
- all authority invocation observations;
- no model-visible behavior change yet;
- maintainers can inspect shadow comparison.

## Change 4 — Add catalogue recovery and uniform deferred read

### Objective

Make initial misses and oversized instructions recoverable.

### Work

- Register `skills.search` independent of orchestrator availability.
- Search the active step snapshot.
- Enforce query/result/call budgets.
- Extend `skills.read` across authority kinds.
- Add generation-bound identities and opaque cursors.
- Add pagination and 1 MiB cap.
- Replace silent selected-body truncation with inline/deferred behavior.
- Preserve existing orchestrator list/read compatibility as required.

### Likely files

```text
codex-rs/ext/skills/src/tools/mod.rs
codex-rs/ext/skills/src/tools/search.rs
codex-rs/ext/skills/src/tools/read.rs
codex-rs/ext/skills/src/tools/schema.rs
codex-rs/ext/skills/src/state.rs
codex-rs/ext/skills/src/extension.rs
codex-rs/ext/skills/tests/skills_extension.rs
codex-rs/core/tests/suite/skills.rs or current equivalent
```

### Exit criteria

- initial miss/recovery/read integration test;
- explicit oversized body complete;
- stale handle tests;
- no enumeration;
- no authority mismatch;
- no silent truncation.

## Change 5 — Active adaptive catalogue cutover

### Objective

Use adaptive candidates when and only when the canonical full render is lossy.

### Work

- Add `Off | Shadow | Active` internal/config mode or equivalent controlled state.
- Probe canonical full render.
- Full mode when lossless.
- Candidate mode when shortened or omitted.
- Pin explicit set and apply closed/open supplement semantics.
- Insert stable recovery guidance.
- Ensure one authoritative skill fragment per model step.
- Remove/disable duplicate legacy injections in active mode.
- Preserve degraded fallback.
- Add prompt/cache/compaction/resume/fork tests.

### Exit criteria

- all deterministic acceptance tests;
- exact prompt snapshots;
- no duplicate catalogue;
- no explicit regression;
- fallback works;
- rollback switch works.

## Change 6 — Diagnostics, full verification, and removal of temporary shadow code

### Objective

Finish the issue, not merely activate code.

### Work

- Add developer routing report/command or existing diagnostic integration.
- Produce acceptance report.
- Run load/benchmark tests.
- Confirm fleet shadow gates with maintainers.
- Switch default to active only after gates.
- Retain an active-versus-control sampling mechanism only if maintainers require it.
- Remove `ShadowSelectionExperiment` temporary code once its purpose is fulfilled, or rename/refactor
  it into permanent evaluation infrastructure.
- Remove dead parallel renderer/selection code.
- Update inline developer/API docs where allowed.
- Do not add general user docs under repository `docs/` contrary to `AGENTS.md`.

### Exit criteria

Every requirement in the traceability matrix is implemented and verified.

## Exact semantic changes to current code

### `ShadowSelectionExperiment`

Current status: temporary, metrics only, top 20, current input only, host/orchestrator observable
sources.

Required outcome:

- selector logic moved into permanent routing modules;
- shadow evaluator compares methods over complete observable ground truth;
- executor/custom structured invocation added;
- active selector reused by candidate and search paths;
- current-only query replaced with bounded current plus prior evidence.

### `WeightedLexicalSkillSelector`

Retain the baseline method/version. Add new fused method rather than silently changing metric meaning.

### `SkillsExtension::contribute`

Current behavior:

- builds catalogue;
- resolves explicit mentions;
- runs shadow selector;
- renders a filtered host-only turn catalogue;
- truncates selected main prompts.

Required:

- consume/publish `SkillRoutingSnapshot`;
- resolve explicit set;
- determine full/adaptive/explicit-only mode;
- render exactly one catalogue;
- inline or defer complete selected instructions;
- publish active step state.

### `ContextContributor::contribute_world_state`

Current behavior projects executor skills separately.

Required:

- participate in building/replacing one authority-neutral step snapshot/catalogue;
- do not independently render a duplicate executor catalogue after cutover.

### `SkillToolAuthority`

Current model-visible tool authority is orchestrator-only.

Required:

- authority-neutral identity validated through active snapshot;
- existing orchestrator calls remain accepted where compatibility demands.

### `SkillProvider::search`

Do not use package-oriented provider search as catalogue search. Leave or rename with clear semantics.

## Migration and feature state

### Existing `skill_search=true`

At pinned baseline it means shadow selector enabled.

Migration options:

```toml
[features.skill_search]
mode = "shadow" # off | shadow | active
```

or an internal rollout requirement without public config.

Do not interpret existing boolean `true` as active behavior without an explicit migration.

### Rollback

Active mode rollback must:

- switch to legacy/full bounded renderer;
- leave explicit resolution and picker unchanged;
- leave inventory caches unchanged;
- disable `skills.search` only if no deferred selected body needs it;
- preserve telemetry reason;
- require no skill reinstallation or config rewrite.

## Review-size discipline

Repository guidance prefers complex changes below 500 changed lines and generally below 800 unless
mechanical. Each change above should be split further if its actual diff exceeds that guidance, but
do not create a state with two active catalogues.

Use dependent branches or stacked PRs. Every intermediate commit must compile and have coherent tests.

## Required commands

Run from `codex-rs` as applicable:

```text
just fmt
just test -p codex-skills-extension
just test -p codex-core-skills
just test -p codex-core
just test -p codex-app-server
just fix -p codex-skills-extension
just fix -p codex-core-skills
just argument-comment-lint
just write-config-schema       # when config changed
just bazel-lock-update         # when Rust dependencies changed
git diff --check
```

Follow `AGENTS.md`: do not run `cargo test` directly. Run the full `just test` according to
maintainer/user approval workflow before final submission.

## Code quality rules

- no `async_trait`;
- document new traits;
- self-documenting enums/newtypes instead of opaque booleans;
- argument comments for positional literals where required;
- exhaustive matches;
- module size targets;
- no test-only public API proliferation;
- integration tests for agent logic;
- bounded `ContextualUserFragment` types;
- no new unbounded model-visible items;
- no item over 10K tokens.

## Pull request description requirements

The final stack descriptions must include:

- exact current/target behavior;
- why the original proposal is superseded;
- why both automatic candidates and recovery search are required;
- authority/snapshot invariants;
- context limits;
- explicit multi-skill semantics;
- security controls;
- tests/benchmarks;
- shadow evidence;
- rollback;
- known skipped tests.

## Upstream submission rule

Do not open an unsolicited large PR before confirming the current contribution policy and discussing
the design in the relevant issue/maintainer channel. The code and documents can be complete locally;
OpenAI maintainers decide review and merge.

When submitted, reference current related issues and prior PRs without claiming that auto-closed or
unmerged PRs were rejected.
