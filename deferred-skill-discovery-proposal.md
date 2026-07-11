# Overflow-aware skill discovery in Codex

A proposal for preserving implicit skill routing when the visible catalog reaches its context budget

Date: July 12, 2026  
Status: Submitted for product and engineering review

## Summary

I use Codex with a large collection of installed skills. My concern is not that Codex loads every `SKILL.md` into every prompt. It does not. Codex already uses progressive disclosure and limits the visible skill catalog to 2% of the model's context window. The full instructions are loaded only after a skill is selected.

The issue is narrower. Once the catalog reaches that limit, Codex shortens descriptions and may eventually omit some implicitly invokable skills from the model-visible list. Those skills still exist in Codex's host catalog. They can still appear in the skill picker and can still be invoked explicitly with `$skill`. But the model cannot select an omitted skill from an ordinary natural-language request because it never sees that skill's metadata.

I am proposing an experiment for that overflow case only. When the renderer has to omit skills, Codex could search the existing host catalog and expose a few relevant candidates. Nothing should change while the catalog fits normally.

This can be tested without building a new database, watcher, plugin scanner, autocomplete system, or semantic index. Codex already has most of the machinery needed.

## What Codex already handles

The public documentation explains the basic progressive-disclosure model. Codex begins with skill names, descriptions, and paths, then reads the selected `SKILL.md`. The visible catalog has a 2% context budget, with an 8,000-character fallback when the context size is unknown. Descriptions are shortened before entries are omitted.

I also reviewed the current open-source implementation. It already contains:

- A `SkillsService` that discovers skills, applies configuration, and caches immutable snapshots by working directory and effective configuration
- An app-server `skills/list` endpoint that uses active plugin roots and current settings
- A `SkillsWatcher` that invalidates cached skill state when local files change
- Path aliasing to reduce catalog cost
- Scope-aware ordering when everything cannot fit
- Renderer metrics for shortened descriptions and omitted entries
- Explicit mention resolution against the full catalog before the bounded model-visible list is constructed
- A host provider that maps `HostSkillsSnapshot` into the skills extension's list and read model

This matters because it changes the shape of the solution. Codex does not need another general-purpose skill registry. It needs a way to search the active host catalog when part of that catalog is absent from model context.

## The specific gap

The current behavior has three cases.

First, the complete metadata fits. There is no problem to solve, and adding retrieval would only create latency and complexity.

Second, descriptions are shortened but all skills remain visible. This might affect routing, but that should be measured. A clear skill name and a shortened description may still be enough.

Third, some skills are omitted. This is the case with the strongest failure mode. An omitted skill cannot participate in implicit selection because the model has no evidence that it exists.

The full host catalog is still available outside the rendered prompt. Explicit mentions are resolved from it, and the client can obtain it through `skills/list`. The missing piece is catalog-level discovery for natural-language requests.

This is a scale threshold, not a universal Codex defect. Before changing the product, it would be useful to know how often real installations cross that threshold and whether omission leads to observable routing failures.

## A small experiment

### Start with measurement

The renderer already knows when it shortens or omits metadata. Codex could expose or aggregate the following facts:

- Number of active, implicitly invokable skills
- Metadata size before and after budgeting
- Number of descriptions shortened
- Number and scope of skills omitted
- Whether the eventual skill selection was explicit or implicit
- Cases where a user explicitly invokes an omitted skill after an earlier request did not select it

These measurements are more reliable than scanning directories. A raw filesystem scan can count disabled skills, duplicate entries, inactive plugin versions, and stale cache files.

The relevant cost is model-visible context, not a claimed per-turn bill. Prompt caching and subscription accounting are separate from the question of whether useful routing metadata occupies the context window.

### Search only when omission occurs

If `SkillRenderReport.omitted_count` is zero, Codex should behave exactly as it does now.

If entries are omitted, Codex could expose a bounded operation such as:

```text
skills.search_catalog(query, limit)
```

The search should run over enabled, implicitly invokable metadata in the existing `HostSkillsSnapshot`. It should not rescan the filesystem or enumerate plugin cache directories.

A result needs only the qualified name, description or short description, scope, source identity, and an opaque handle that Codex can use to load the skill. The number of results and total output must be capped.

The skills extension already has a provider `search` method, but that request is scoped to resources inside a known package. Catalog discovery is a different operation and should use a separate contract.

### Keep the first ranking method boring

Skill descriptions are written specifically for routing. A first implementation can rank exact names, qualified names, phrases, tokens, and spelling variations. Repository-scoped skills can receive a small boost when the task belongs to that repository.

There is no need to begin with embeddings. If lexical retrieval performs poorly, the evaluation will provide concrete examples for semantic reranking. Starting with a persistent vector index would add storage, invalidation, privacy, and dependency questions before anyone knows whether it is necessary.

## Two ways to use the search

One option is model-triggered search. When entries are omitted, the visible catalog would include a short notice:

```text
Additional enabled skills were omitted from this bounded list. Use skills.search_catalog when the task may require an unlisted skill.
```

This avoids retrieval when the visible list is sufficient and lets the model reformulate its query. The downside is that the model may fail to call the search tool, and every call adds a round trip.

The other option is automatic retrieval. When omission occurs, the harness would search overflow metadata using the current user message and merge a few candidates into the visible list before the model runs. This avoids a tool round trip, but retrieval would run on every affected turn. Weak matches could also crowd out more useful metadata.

I do not think the proposal should choose between these approaches without an evaluation. Both are small enough to test.

Explicit `$skill` mentions should remain untouched. The skill picker should continue using the full app-server list. This proposal is only about implicit discovery of overflow entries.

## Scope, safety, and precedence

Search results must come from the same configured snapshot that Codex already trusts for the turn. Disabled skills, inactive plugin versions, and skills with implicit invocation disabled must not appear.

Exact qualified-name matches should rank first. Repository scope can influence relevance, but search should retain source identity when two active skills share a display name. The current system, admin, repository, and user scope rules should continue to determine which skills are active.

Searching metadata must not execute scripts, install dependencies, open references, or read arbitrary paths. Skill contents should still be loaded through the owning provider and the existing approval and trust boundaries. Opaque handles are preferable to paths in search results.

## How to evaluate it

The important metric is whether Codex finds the right skill, not how much metadata it can remove.

A useful test set would include ordinary requests with one intended skill, ambiguous requests, and requests where no skill should run. It should cover intended skills both inside and outside the visible budget. It should also include duplicate names, repository and user scope conflicts, disabled implicit invocation, plugin upgrades with stale cache versions, and skill installation or removal during a running session.

Three conditions should be compared:

1. The current bounded catalog
2. The bounded catalog with model-triggered overflow search
3. The bounded catalog with automatic overflow retrieval

For each condition, measure correct skill selection, recall at several candidate limits, inappropriate activation, added input tokens, removed catalog tokens, and end-to-end latency. The test should also track whether the model failed to search when it should have and whether skill changes became visible promptly.

An experiment succeeds only if omitted-skill recall improves without a meaningful regression for already visible skills or negative prompts. Exact explicit mentions must remain unchanged. Search output must stay smaller than the metadata it replaces, and the current behavior must remain available as a fallback.

Numeric thresholds should be chosen after a baseline exists. Picking a latency target or percentage improvement now would give a false sense of precision.

## Suggested rollout

Start by exposing diagnostics for active skill count, metadata cost, truncation, omission, and scope distribution. That establishes whether the problem is common enough to justify product work.

Next, add catalog search over `HostSkillsSnapshot` behind a feature flag and run the three-way evaluation. If one strategy improves routing, offer it as an opt-in recovery path only when omission occurs.

It should become a default only if the data shows better recall without unacceptable latency or false activation. Keeping the current implementation is a valid outcome if omission is rare or harmless in practice.

## Alternatives worth comparing

Increasing the 2% budget would postpone omission, but it would consume more context and would not scale indefinitely. It is still useful as an experimental control.

Shorter skill descriptions help while the skill remains visible. They cannot help after an entry has been omitted.

Users can disable skills or scope them to repositories today. That may be the right operational advice for many installations, although it gives users the job of maintaining the catalog.

Exposing the complete host catalog through model-facing `skills.list` and `skills.read` tools would reuse the orchestrator tool shape, but listing everything on demand could recreate the same context cost. Bounded catalog search is a better fit for this problem.

## Questions for the Codex team

1. How often do renderer metrics show description truncation or skill omission in real installations?
2. Is there evidence that omitted or heavily shortened metadata causes implicit routing failures?
3. Is catalog-level host skill search already planned within the skills extension?
4. Would an overflow-only experiment fit the existing `SkillsService`, `HostSkillsSnapshot`, and extension architecture?
5. Should model-triggered and automatic recovery both be evaluated?
6. Could renderer diagnostics be exposed so user reports contain active-catalog facts rather than raw filesystem counts?

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

I am Binil Thomas Scaria, a Chartered Accountant and self-described "vibe-coder" from Kerala, India. I have used ChatGPT since the day it launched, and I now use Codex to build the core product for my SaaS startup idea.

Email: [binilts33@gmail.com](mailto:binilts33@gmail.com)  
Phone: [+91 96454 38545](tel:+919645438545)
