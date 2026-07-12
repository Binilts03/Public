# Overflow-aware skill discovery in Codex

Preserving implicit skill routing when the model-visible catalog reaches its context budget

Date: July 12, 2026  
Status: Proposal for product and engineering review

## Summary

Codex already handles skill context efficiently. It exposes a bounded metadata catalog to the model and loads the full `SKILL.md` only after selecting a skill. The catalog is limited to 2% of the model's context window, with an 8,000-character fallback when the context size is unknown. Codex shortens descriptions first and omits entries only when the minimum metadata still does not fit.

The remaining problem is limited to catalog overflow. An omitted skill remains available to the host, the skill picker, and explicit `$skill` invocation, but it cannot be selected implicitly from a natural-language request because the model never sees its metadata.

This proposal recommends an overflow-only experiment. When the renderer omits skills, Codex should search the existing active host catalog and expose a small set of relevant candidates. Current behavior should remain unchanged when the catalog fits.

The experiment can reuse existing Codex infrastructure. It does not require another persistent index, filesystem watcher, plugin scanner, autocomplete system, or skill format.

## Current behavior

The public documentation describes progressive disclosure for skills: the model initially receives names, descriptions, and paths, then Codex reads the selected skill's instructions. Skills support both explicit and implicit invocation.

The current open-source implementation provides additional safeguards:

- `SkillsService` discovers skills, applies effective configuration, and caches immutable snapshots by working directory and configuration.
- The app server exposes `skills/list` using current plugin roots and settings.
- `SkillsWatcher` invalidates cached skill state when applicable local files change.
- The renderer uses path aliases when they reduce metadata cost.
- Descriptions are shortened before entries are omitted.
- Scope ordering protects system, admin, and repository skills before user-scoped skills when space is limited.
- The renderer records truncation and omission metrics.
- Explicit mentions are resolved from the full catalog before the bounded model-visible catalog is constructed.
- `HostSkillProvider` maps the active host snapshot into the skills extension's list and read model.

These components already solve discovery, activation, caching, change detection, and explicit invocation. The missing capability is bounded catalog search for implicit routing when entries are omitted from model context.

## Problem statement

The catalog budget produces three cases.

1. All metadata fits. No retrieval is needed.
2. Descriptions are shortened, but every skill remains visible. Routing may still work from the name and shortened description.
3. Some entries are omitted. Those skills cannot participate in implicit selection because their metadata is absent from the model-visible list.

Only the third case has a definite discovery failure. Description truncation may also reduce routing quality, but that should be established through measurement rather than assumed.

This is a scale threshold, not a universal defect. The product question is narrow:

> When the renderer must omit implicitly invokable skills, can Codex recover relevant overflow entries without placing the complete catalog in model context?

## Measure before changing defaults

The renderer already knows whether it shortened or omitted metadata. Product diagnostics should report:

- Active implicitly invokable skill count
- Metadata cost before and after budgeting
- Number of shortened descriptions
- Number and scope of omitted entries
- Explicit versus implicit skill selection
- Cases where an omitted skill is invoked explicitly after an earlier natural-language request did not select it

These measurements are more reliable than scanning directories. A filesystem scan can count disabled skills, duplicates, inactive plugin versions, and stale cache files.

The proposal concerns model-visible context and routing recall. It should not claim a fixed per-turn financial cost because prompt caching, subscription accounting, and backend request handling are separate concerns.

## Proposed experiment

### Gate on actual omission

Overflow discovery should run only when `SkillRenderReport.omitted_count` is greater than zero. If the existing renderer fits every skill after aliasing and description shortening, Codex should behave exactly as it does today.

Description truncation should be instrumented separately. It should trigger retrieval only if data shows a measurable routing problem.

### Search the active host snapshot

Add a bounded catalog operation with a contract similar to:

```text
skills.search_catalog(query, limit)
```

The operation should search enabled, implicitly invokable metadata in the same `HostSkillsSnapshot` used for the turn. It must not rescan the filesystem or enumerate plugin cache directories.

Each result should contain only what the model needs to choose a skill:

- Qualified name
- Description or short description
- Scope and source identity
- Opaque package or resource handle
- Whether the entry was omitted from the current visible catalog

Both result count and output size must be bounded.

The existing provider `search` method is package-oriented and searches resources inside a known package. Catalog discovery is a separate concern and should use a separate request shape.

### Begin with lexical ranking

Skill metadata is written for routing, so the first implementation should use deterministic local matching over qualified names, descriptions, short descriptions, and trigger metadata. Exact name matches should rank first. Phrase, token, and trigram matching can handle ordinary wording and spelling variation. Repository-scoped skills may receive a small boost for tasks in that repository.

Embeddings should not be part of the first experiment. A vector index would add storage, invalidation, privacy, and dependency concerns before lexical retrieval has been shown inadequate.

## Invocation strategies

Two approaches should be compared.

### Model-triggered search

When entries are omitted, append a compact instruction to the visible catalog:

```text
Additional enabled skills were omitted from this bounded list. Use skills.search_catalog when the task may require an unlisted skill.
```

This avoids retrieval when the visible catalog is sufficient and lets the model reformulate its query. It also adds a tool round trip and depends on the model recognizing when search is needed.

### Automatic overflow retrieval

When omission occurs, the harness searches overflow metadata using the current user message before the first model call and merges a few candidates into the visible list.

This removes the tool round trip but runs retrieval on every affected turn. Weak matches could also displace more useful metadata.

Neither approach should become the default without comparative evaluation. Explicit mentions and the client skill picker should remain unchanged.

## Scope and safety

Search results must come from the configured snapshot already trusted for the turn. Disabled skills, inactive plugin versions, and skills with implicit invocation disabled must not appear.

Exact qualified-name matches should take precedence. Duplicate display names must retain distinct source identities. Existing scope rules should continue to decide which skills are active.

Catalog search must not execute scripts, install dependencies, open references, or read arbitrary paths. Skill contents should still be loaded through the owning provider and current trust and approval boundaries. Opaque handles are preferable to raw paths in search results.

## Evaluation

The primary metric is correct skill selection, not maximum token reduction.

The test corpus should include:

- Natural-language requests with one intended skill
- Ambiguous requests with several plausible skills
- Requests where no skill should activate
- Intended skills both inside and outside the visible budget
- Duplicate names across sources
- Repository and user scope conflicts
- Skills with implicit invocation disabled
- Plugin upgrades with stale cache versions on disk
- Installation, editing, disabling, and removal during a running session

Compare three conditions:

1. Current bounded catalog
2. Bounded catalog with model-triggered overflow search
3. Bounded catalog with automatic overflow retrieval

Measure correct selection rate, recall at several candidate limits, inappropriate activation, added input tokens, removed catalog tokens, search usage, missed-search cases, end-to-end latency, and freshness after skill changes.

An experiment succeeds only if omitted-skill recall improves without a material regression for visible skills or negative prompts. Exact explicit invocation must remain unchanged. Search output must remain smaller than the metadata it replaces, and the current renderer must remain available as a fallback.

Numeric thresholds should be set after establishing a baseline.

## Rollout

1. Expose diagnostics for active count, metadata cost, truncation, omission, and scope distribution.
2. Add host catalog search behind a feature flag and run the three-way evaluation.
3. Offer the better-performing strategy as an opt-in recovery path only when omission occurs.
4. Make it the default only if it improves recall without unacceptable latency or false activation.

Keeping the current implementation is a valid outcome if omission is rare or does not cause meaningful routing failures.

## Alternatives

Increasing the 2% budget would postpone omission but consume more context. It is useful as an experimental control, not a scalable solution.

Shorter descriptions help while an entry remains visible. They cannot help after omission.

Users can disable skills or scope them to repositories. That may be sufficient for many installations, but it requires users to maintain availability manually.

Exposing the complete host catalog through model-facing `skills.list` and `skills.read` tools would reuse the orchestrator tool shape. Listing everything on demand could recreate the same context cost, so bounded search is a better fit for implicit discovery.

## Questions for the Codex team

1. How often do renderer metrics show description truncation or skill omission in active installations?
2. Is there evidence that omitted or heavily shortened metadata causes implicit routing failures?
3. Is catalog-level host skill search already planned within the skills extension?
4. Would an overflow-only experiment fit the current `SkillsService`, `HostSkillsSnapshot`, and extension architecture?
5. Should model-triggered and automatic recovery both be evaluated?
6. Can renderer diagnostics be exposed so user reports contain active-catalog facts instead of raw filesystem counts?

## Sources

Public documentation:

- [Build skills: progressive disclosure, budget, invocation, locations, and enablement](https://developers.openai.com/codex/skills)
- [Codex configuration reference: `skills.config`](https://developers.openai.com/codex/config-reference)
- [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)

Open-source implementation reviewed at commit [`9e552e9d15ba52bed7077d5357f3e18e330f8f38`](https://github.com/openai/codex/commit/9e552e9d15ba52bed7077d5357f3e18e330f8f38):

- [Skill metadata budgeting, aliases, ordering, and renderer report](https://github.com/openai/codex/blob/9e552e9d15ba52bed7077d5357f3e18e330f8f38/codex-rs/core-skills/src/render.rs)
- [Cached host skill snapshots and configuration-aware loading](https://github.com/openai/codex/blob/9e552e9d15ba52bed7077d5357f3e18e330f8f38/codex-rs/core-skills/src/service.rs)
- [App-server skill watching and cache invalidation](https://github.com/openai/codex/blob/9e552e9d15ba52bed7077d5357f3e18e330f8f38/codex-rs/app-server/src/skills_watcher.rs)
- [Full app-server `skills/list` path](https://github.com/openai/codex/blob/9e552e9d15ba52bed7077d5357f3e18e330f8f38/codex-rs/app-server/src/request_processors/catalog_processor.rs)
- [Host skill provider backed by `HostSkillsSnapshot`](https://github.com/openai/codex/blob/9e552e9d15ba52bed7077d5357f3e18e330f8f38/codex-rs/ext/skills/src/provider/host.rs)
- [Skill extension catalog construction and explicit mention loading](https://github.com/openai/codex/blob/9e552e9d15ba52bed7077d5357f3e18e330f8f38/codex-rs/ext/skills/src/extension.rs)
- [Current orchestrator-only model-facing `skills.list` tool](https://github.com/openai/codex/blob/9e552e9d15ba52bed7077d5357f3e18e330f8f38/codex-rs/ext/skills/src/tools/list.rs)
