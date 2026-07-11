# Proposal: overflow-aware skill discovery for Codex

Preserving implicit skill routing when the model-visible catalog reaches its context budget

Date: July 12, 2026  
Status: Revised problem statement and minimal product experiment

## Executive summary

Codex already handles large skill collections more carefully than a simple directory scan would suggest. It loads active skills into a cached, scope-aware host snapshot, resolves explicit skill mentions from the full catalog, provides the client with a complete `skills/list` API, watches local skill roots for changes, aliases long paths when useful, and limits the model-visible skill catalog to 2% of the model context window. Full `SKILL.md` instructions are loaded only after a skill is selected.

This means the original concern is not a universal token-growth defect. Codex already bounds that cost. The narrower problem appears only when the model-visible catalog reaches its budget: descriptions may be shortened, and eventually some implicitly invokable skills are omitted from the model-visible list. Explicit `$skill` invocation and the skill picker can still use the full host catalog, but natural-language implicit routing cannot select metadata the model never received.

The proposed change is therefore small:

1. Instrument how often truncation and omission occur and whether they correlate with missed implicit routing.
2. When skills are actually omitted, expose an overflow-search capability backed by the existing host skill snapshot.
3. Compare model-triggered search with automatic retrieval before changing default behavior.

The minimum viable experiment requires no new persistent database, filesystem watcher, plugin scanner, skill format, semantic index, or autocomplete system. Those components already exist or are unnecessary for the first test.

## What Codex already does

The public documentation says Codex uses progressive disclosure. The model initially sees each implicitly invokable skill's name, description, and path, while the full `SKILL.md` is loaded only after selection. The initial skill list is limited to 2% of the model context window, or 8,000 characters when the context window is unknown. Codex shortens descriptions first and may omit skills if the minimum metadata still does not fit.

The current open-source implementation adds important detail:

- `SkillsService` discovers host skills, applies configuration, caches immutable snapshots by working directory and effective configuration, and exposes cache invalidation.
- The app server exposes `skills/list` using the active plugin roots and current configuration.
- `SkillsWatcher` watches applicable local roots, clears the cache when files change, and emits a `skills/changed` notification.
- The renderer tries absolute and aliased paths, shortens descriptions before omission, records omission and truncation metrics, and orders protected scopes before user-scoped skills.
- The skills extension resolves explicit mentions from the full turn catalog before constructing the bounded model-visible catalog.
- A host skill provider already maps the host snapshot into an authority-aware list and read contract.
- Model-facing `skills.list` and `skills.read` tools exist for orchestrator-owned skills, although host-owned catalog search is not currently exposed through that interface.

These findings remove most of the infrastructure proposed in the earlier draft.

## Corrected problem statement

This is a threshold problem, not a problem every Codex user experiences.

For small and medium catalogs, the current implementation is simpler and likely preferable. Every implicitly invokable skill can remain visible, descriptions retain enough trigger language, and no retrieval step is needed.

When the catalog reaches its budget, Codex degrades in two stages:

1. Descriptions are shortened while skill names and paths remain visible.
2. If minimum metadata still cannot fit, lower-priority skills are omitted from the model-visible list.

The first stage may or may not cause meaningful routing failures. A well-named skill can remain discoverable from a shortened description. The second stage has a clearer limitation: an omitted skill cannot be selected implicitly from natural language because the model has no metadata for it.

The full catalog still exists outside the rendered prompt. Explicit mentions and client-side browsing are separate paths and should not be described as broken by metadata omission.

The product question is therefore:

> When the current renderer must omit implicitly invokable skills, can Codex recover relevant overflow skills without placing the full catalog in model context?

## Evidence and uncertainty

A local exploratory scanner found more than 200 candidate skill files across user directories and plugin caches. That result explains how a user can reach the documented budget, but it is not reliable product evidence by itself. A raw cache scan can count inactive plugin versions, duplicate skills, disabled skills, and files outside the effective configuration.

The Codex team's own renderer report is the authoritative measurement because it operates on the active, configured host snapshot. Before prioritizing a routing change, Codex should measure:

- Active implicitly invokable skill count
- Full metadata cost before budgeting
- Rendered metadata cost
- Number and extent of shortened descriptions
- Number and scope of omitted skills
- Whether the selected skill was explicit or implicit
- Cases where users subsequently invoke an omitted skill explicitly after an implicit miss
- Catalog-budget warnings shown per active installation

The proposal should not claim a specific recurring billing cost. Prompt caching, request construction, subscription accounting, and backend reuse are separate concerns. The defensible claim is about model-visible context occupancy and missing routing metadata.

## Goals

- Preserve current behavior when no skills are omitted.
- Improve implicit routing recall for skills outside the bounded visible catalog.
- Reuse the active host snapshot and existing configuration semantics.
- Keep explicit invocation and the client skill picker unchanged.
- Avoid sending the complete overflow catalog to the model.
- Add no network dependency and execute no skill code during discovery.
- Measure false positives, false negatives, latency, and context cost before changing defaults.
- Fall back to the current renderer if overflow discovery is unavailable.

## Non-goals

- Replacing the current bounded catalog for all users
- Building another filesystem index or watcher
- Changing `SKILL.md` or `agents/openai.yaml`
- Reworking plugin installation or activation
- Adding embeddings in the first implementation
- Searching inside a selected skill's reference files
- Solving general tool discovery
- Changing explicit `$skill` resolution or autocomplete

## Proposed minimum viable experiment

### 1. Use the existing renderer report as the gate

Run overflow discovery only when `SkillRenderReport.omitted_count` is greater than zero. If the current catalog fits after path aliasing and description shortening, preserve today's behavior exactly.

Description truncation can be instrumented separately. It should not trigger a new retrieval path until data shows that truncation alone causes material routing failures.

### 2. Search the existing active host catalog

Add a catalog-level operation with a narrow contract, for example:

```text
skills.search_catalog(query, limit)
```

The operation should search enabled, prompt-visible host skill metadata from the same `HostSkillsSnapshot` already used to render the turn catalog. It should not rescan the filesystem or inspect raw plugin cache directories.

Each result should contain only the metadata needed for selection:

- Qualified name
- Description or short description
- Scope and source identity
- Opaque package or resource handle
- Whether the entry was omitted from the current model-visible catalog

The result count and total output size must be bounded.

The existing provider `search` method is package-oriented and intended for searching resources inside a known package. Catalog discovery is a different operation and should have a separate name and request shape.

### 3. Start with deterministic lexical ranking

The first implementation should rank skill names, qualified names, descriptions, short descriptions, and trigger metadata using inexpensive local matching. Exact name matches should dominate. Token, phrase, and trigram matching are sufficient for an experiment.

Do not add embeddings until the lexical baseline is measured. Skill descriptions are already written as routing metadata, so lexical retrieval may be adequate. If it is not, the evaluation will show where semantic reranking helps.

### 4. Test two invocation strategies

#### Strategy A: model-triggered search

When the renderer omits skills, append a compact notice such as:

```text
Additional enabled skills were omitted from this bounded list. Use skills.search_catalog when the task may require an unlisted skill.
```

Advantages:

- No retrieval work when the visible catalog is sufficient
- The model can reformulate the search query
- Search results enter context only when requested

Risks:

- The model may not call the tool when it should
- A tool round trip adds latency
- A generic instruction may itself be ignored

#### Strategy B: automatic overflow retrieval

When omission occurs, the harness searches overflow metadata using the current user message before the first model call and merges a small number of candidates into the visible catalog.

Advantages:

- No extra model round trip
- The model always receives likely overflow candidates

Risks:

- Retrieval runs on every affected turn
- Poor ranking can crowd out better visible metadata
- The raw user message may not contain enough routing language

Both strategies should be evaluated. The proposal should not choose one without data.

### 5. Preserve existing explicit behavior

Explicit skill mentions should continue to resolve from the full catalog and load the selected skill directly. The skill picker should continue using the app server's full `skills/list` response.

No new index or autocomplete API is needed for this proposal.

## Scope and precedence

The current renderer prioritizes system, admin, repository, and user scopes in that order when metadata cannot fit. Overflow search must preserve scope and source identity but should not blindly reproduce prompt ordering as relevance ranking.

A reasonable policy is:

- Exact explicit mention always wins.
- Exact qualified-name match wins within search.
- Repository-scoped candidates receive a small relevance boost for tasks in that repository.
- Disabled entries and entries with implicit invocation disabled are never returned for implicit search.
- Duplicate display names retain distinct qualified identities.
- Active plugin roots come from the existing effective configuration, not disk-cache enumeration.

## Security and privacy

The experiment should use metadata already loaded by Codex. It must not execute scripts, load references, install dependencies, or read arbitrary paths during search.

Search results should return opaque handles where possible. Skill contents should still be read through the owning provider and current approval and trust boundaries. Disabled skills and inactive plugin versions must remain unavailable.

The local query and catalog need not leave the machine except for the small candidate metadata eventually included in model context, which is consistent with current skill rendering.

## Evaluation plan

The main question is routing recall, not maximum token reduction.

Build a test corpus containing:

- Natural-language prompts with one intended skill
- Prompts with several plausible skills
- Prompts where no skill should activate
- Intended skills retained in the visible catalog
- Intended skills omitted by the budget
- Duplicate names across sources
- Repository and user scope conflicts
- Skills with implicit invocation disabled
- Newly installed, edited, disabled, and removed skills
- Active plugins with stale cache versions still present on disk

Compare three conditions:

1. Current bounded catalog
2. Bounded catalog plus model-triggered overflow search
3. Bounded catalog plus automatic overflow retrieval

Report:

- Correct skill selection rate
- Recall at candidate limits 3, 5, and 8
- Inappropriate skill activation rate
- Search invocation rate and missed-search rate
- Added input tokens
- Tokens removed from the initial catalog
- End-to-end latency
- Cache invalidation and freshness failures

Acceptance criteria for an experiment:

- Exact explicit mentions remain unchanged.
- No disabled or non-implicit skill appears in implicit results.
- Omitted-skill routing recall improves materially over the current baseline.
- Routing for skills already visible does not regress materially.
- Negative-prompt false activation does not increase materially.
- Search output is bounded and lower than the metadata it replaces.
- Current behavior remains available as a fallback.

Numeric quality thresholds should be set after establishing a baseline. The earlier draft's specific latency and percentage targets were arbitrary and have been removed.

## Rollout

### Phase 1: diagnostics

Expose renderer diagnostics in developer settings or logs: active count, metadata cost, truncation count, omission count, and scope distribution. This establishes whether the problem is common enough to prioritize.

### Phase 2: internal evaluation

Implement catalog search over `HostSkillsSnapshot` behind a feature flag. Run the three-way routing evaluation without changing user defaults.

### Phase 3: opt-in overflow recovery

Enable the better-performing strategy only when omission occurs. Keep the current catalog and fallback path.

### Phase 4: default only if justified

Make overflow recovery the default only if it improves omitted-skill recall without meaningful regressions in normal routing, latency, or false activation.

## Alternatives

### Keep the current implementation

This remains a reasonable outcome if omission is rare or does not cause meaningful failures. Instrumentation should come before architectural work.

### Increase the 2% budget

This delays omission but consumes more context and does not scale indefinitely. It is a useful experimental control, not a complete solution.

### Shorten or improve skill descriptions

Better descriptions help before omission and should remain recommended authoring practice. They cannot help a skill whose metadata is absent from the model-visible list.

### Require users to disable or scope skills

This is available today and may be the right operational advice. It shifts catalog management to users and does not preserve universal implicit availability.

### Expose full host `skills.list` and `skills.read` tools

This would reuse the existing orchestrator tool shape, but listing the entire host catalog on demand can recreate the original context cost. A bounded catalog-search operation is better suited to implicit discovery. Host list and read support may still be useful for other workflows.

### Build a persistent semantic index

The current host snapshot already contains the metadata needed for a first experiment. A persistent semantic index adds storage, invalidation, privacy, and dependency questions before lexical retrieval has been shown inadequate.

## Requested review

I would appreciate the Codex team's guidance on these questions:

1. How often do current renderer metrics show description truncation or skill omission in real installations?
2. Does the team have evidence that omitted or heavily shortened metadata causes implicit routing failures?
3. Is catalog-level host skill search already planned within the skills extension?
4. Would an overflow-only experiment fit the current `SkillsService`, `HostSkillsSnapshot`, and extension architecture?
5. Should overflow recovery be model-triggered, automatic, or evaluated both ways?
6. Can renderer diagnostics be exposed to users so reports include active-catalog facts rather than raw filesystem counts?

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

## About the author

Binil Thomas Scaria is a Chartered Accountant and self-described "vibe-coder" from Kerala, India. He has used ChatGPT since the day it launched and currently uses Codex to build the core product for his SaaS startup idea.

Email: [binilts33@gmail.com](mailto:binilts33@gmail.com)  
Phone: [+91 96454 38545](tel:+919645438545)
