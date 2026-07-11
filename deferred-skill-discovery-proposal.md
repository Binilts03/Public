# Proposal: deferred skill discovery for Codex

Reducing skill-catalog context while preserving explicit invocation, implicit routing, and newly installed skills

Date: July 12, 2026  
Status: Problem statement and proposed product design for review

## Executive summary

Codex already uses progressive disclosure for skills. It initially provides the model with each available skill's name, description, and path, then loads the full `SKILL.md` only when a skill is selected.

That design works well for a modest skill collection. It becomes less effective when a user installs hundreds of skills or enables plugins that contribute many more. At that point, two problems appear:

1. The initial catalog consumes a meaningful, recurring portion of the model context.
2. Description truncation and skill omission make implicit routing less reliable precisely when the user has the most capabilities available.

This proposal adds one more level of progressive disclosure. Codex would keep the complete skill catalog in a host-side index, retrieve a small candidate set for each task, and expose only those candidates to the model.

The requested change is not to remove the existing progressive-disclosure system. It is to move first-stage skill discovery from prompt text into the Codex harness or client.

## Current behavior

The public Codex documentation describes the following behavior:

- Codex initially receives each skill's name, description, and file path.
- Codex loads the full `SKILL.md` only after selecting a skill.
- Skills can be invoked explicitly through a `$skill` mention or implicitly when a task matches the skill description.
- The initial catalog uses at most 2% of the model context window. If the context size is unknown, Codex uses an 8,000-character limit.
- When the catalog is too large, descriptions are shortened first and some skills may be omitted.
- Users can disable individual skills through `[[skills.config]]`, but disabling a skill removes it from normal availability rather than making it lazily discoverable.

These are sensible safeguards. They bound prompt growth and avoid loading complete skill bodies unnecessarily. The remaining issue is that metadata discovery itself is still prompt based.

## Observed scale

In one real Codex installation, a local inventory utility found 241 candidate skill entries across user skill directories and plugin caches. The raw names, descriptions, and paths represented approximately 70–100 KB of prompt text before shorting or omission.

The 241-entry figure is an inventory upper bound, not an exact count of active skills. A naive scan of the complete plugin cache can include old plugin versions and duplicates. That distinction exposes the difference between installed files and active capabilities.

For a model with a 400,000-token context window, the documented 2% catalog limit is approximately 8,000 tokens. This prevents unbounded growth, but 8,000 tokens is still substantial for routing metadata.

## Problem statement

Codex currently asks the model to perform two different jobs from the same initial catalog:

1. Discover which skills might apply.
2. Select and follow the best skill.

The model needs the full instructions only for the second job. It does not need every skill description in context to perform the first job if the host can retrieve likely candidates.

The current catalog cap creates an unavoidable tradeoff:

- A larger catalog gives the model more routing information but consumes more context.
- A smaller or truncated catalog saves context but lowers the chance that the right skill is considered.

A user-authored router skill cannot resolve this tradeoff. Codex builds the available-skills catalog before deciding whether to invoke that router. The router therefore runs after the metadata cost has already been paid.

The problem belongs at the harness or client layer, where discovery can happen before model context is assembled.

## Goals

The proposed design should:

- Reduce initial skill metadata in model context from a function of total installed skills to a small, bounded candidate set.
- Preserve exact `$skill-name` invocation and skill-picker autocomplete.
- Preserve implicit skill selection for natural-language tasks.
- Continue loading the complete, unchanged `SKILL.md` after selection.
- Discover newly installed, updated, enabled, or disabled skills automatically.
- Respect repository, user, admin, system, and plugin skill scopes.
- Index only active plugin versions and honor configuration-based enablement.
- Preserve existing trust, approval, sandbox, and dependency behavior.
- Fail safely by falling back to the current catalog path when retrieval is unavailable.

## Non-goals

This proposal does not attempt to:

- Change the Agent Skills format.
- Rewrite third-party skill descriptions.
- Execute skill scripts during indexing or routing.
- Replace the model's final judgment about which skill to use.
- Require skill authors to assign every skill to a fixed taxonomy.
- Introduce a network service for local skill discovery.

## Proposed design

### 1. Maintain a host-side skill index

Codex should maintain a local index containing the routing metadata it already extracts:

- Qualified name and display name
- Description and optional trigger metadata
- Canonical `SKILL.md` path
- Scope and source
- Plugin identifier and active version, where applicable
- Enablement and implicit-invocation policy
- Content hash or modification timestamp

The index could be in memory, SQLite backed, or integrated with existing Codex state. The storage choice is less important than its behavior. It should be local, fast, invalidated when skill files change, and authoritative about activation state.

The indexer should parse only metadata. It must not execute scripts, install dependencies, or load referenced files. It should apply file-size and parsing limits, canonicalize paths, and follow the same sandbox/approval rules used for skill loading.

### 2. Resolve explicit invocation without model discovery

When a user selects or types `$skill-name`, the client already knows the intended skill. The client should resolve that name directly against the local index and attach the selected skill to the request without loading a full metadata catalog into model context.

The skill picker should query the same index. This preserves autocomplete, browsing, namespaced skills, and exact invocation even when no leaf-skill catalog is present in model context.

### 3. Retrieve candidates for implicit invocation

For an ordinary natural-language task, the harness should search the local index before assembling model context. A practical first version can use:

- Exact and normalized name matching
- Phrase and token matching over descriptions and trigger metadata
- Trigram or fuzzy matching for spelling variation
- BM25 or another inexpensive local ranking method
- Optional semantic reranking when a suitable local or existing embedding facility is available

The search should return a small candidate set, such as the top five to eight skills. The model then receives the complete metadata for those candidates and decides whether any should be loaded.

This keeps model judgment in the loop. The retriever narrows the search space; it does not make the final workflow decision.

### 4. Add low-confidence recovery

Retrieval will occasionally be uncertain. Codex should detect that condition rather than silently missing a skill.

If no candidate reaches a minimum confidence threshold, or if the model says the candidates do not fit, Codex should support a second search with a rewritten query, a larger result set, or a category-based widening. If recovery still fails, the harness should fall back to the current bounded catalog.

This recovery path matters more than choosing a sophisticated ranking algorithm on day one. A simple retriever with visible uncertainty and widening is safer than an opaque retriever that always returns a fixed set.

### 5. Keep existing skill loading unchanged

After selection, Codex should read the selected `SKILL.md` exactly as it does today. References, scripts, assets, dependencies, and related instructions remain lazily loaded according to the skill's workflow.

This limits the proposed change to discovery. It does not alter skill semantics or require authors to republish existing skills.

### 6. Update the index automatically

The registry should react to:

- Skill installation and removal
- `SKILL.md` edits
- Plugin installation, upgrade, enablement, and disablement
- Changes to `skills.config`
- Repository changes that alter applicable `.agents/skills` directories
- Current-working-directory or repository-root changes

File watching can provide fast updates, with a content-hash scan as a fallback. Installers and plugin managers can also emit an explicit invalidation event. A newly installed skill should become available automatically within a short time window.

### 7. Deduplicate and select active sources

The index must distinguish between installed files and active capabilities. It should not route to an old plugin version merely because that version remains in a cache directory.

Duplicate handling should use qualified names, source scope, plugin activation state, and precedence rules. If two active skills legitimately share a name, the picker should disambiguate them and include source identity in the selection UI.

## Request flow

The implicit path would be:

```text
User prompt
    -> local skill index search
    -> top candidate metadata
    -> model selects zero or more skills
    -> Codex loads selected SKILL.md files
    -> task execution continues
```

The explicit path would be:

```text
User selects $skill-name
    -> client resolves exact skill in local index
    -> Codex loads that SKILL.md
    -> task execution continues
```

The second path requires no model-based discovery.

## Expected effect on context use

The current initial metadata cost grows until it reaches the catalog budget. The proposed cost would contain:

- A small, stable description of the discovery capability
- Metadata for only the retrieved candidates
- The selected skill body, which Codex already loads today

For a catalog with more than 200 skills, this should reduce initial skill metadata by well over 90% in typical turns. Exact savings should be measured from the rendered prompt rather than estimated from counts.

Prompt caching is helpful but does not replace this change. Caching can reduce latency and input cost for repeated prefixes, while the cached content still occupies the model context and counts toward token budgets.

## Compatibility requirements

The change should be considered compatible only if it preserves these behaviors:

| Behavior | Required result |
| --- | --- |
| `$skill-name` mention | Resolves exactly and loads the same skill as today |
| Skill picker | Lists all applicable active skills without injecting them all into model context |
| Natural-language task | Retrieves and exposes relevant candidates automatically |
| Selected skill | Loads the complete existing `SKILL.md` without rewriting it |
| Repository-scoped skill | Appears only in applicable repository and directory scopes |
| New installation | Becomes searchable and selectable automatically |
| Plugin upgrade | Uses the active version and ignores stale cache copies |
| Duplicate name | Preserves source identity and supports disambiguation |
| Index failure | Falls back to the current bounded catalog behavior |

## Security and privacy

The index should remain local. It should contain metadata only, and Codex should send only retrieved candidate metadata and selected skill instructions to the model.

Indexing must not execute any code. The loader should retain existing approval, sandbox, dependency, and trust checks. Canonical path validation is necessary so a crafted skill cannot make the index reference unexpected files.

Plugin activation state is also a security boundary. A stale or disabled plugin skill should never become executable merely because its files remain on disk.

## Evaluation plan

A claim of "no quality loss" should be tested rather than assumed. The new path should be compared with the current native catalog on the same prompt set.

The evaluation suite should include:

- Exact `$skill-name` invocations
- Common implicit-routing prompts
- Ambiguous prompts that could match several skills
- Prompts requiring a skill likely to be omitted from a large native catalog
- Negative prompts where no skill should be selected
- Duplicate names and namespaced plugin skills
- Newly installed, edited, disabled, and removed skills
- Plugin upgrades with stale cache versions present
- Repository-scope changes
- Index corruption and unavailable-index fallbacks

Suggested acceptance criteria:

- 100% correct resolution for valid exact skill mentions
- Byte-identical loading of selected `SKILL.md` content
- Implicit-routing recall at top five that is no worse than the current catalog baseline
- No increase in inappropriate skill activation on the negative test set
- More than 90% reduction in initial skill metadata for a 200-skill test installation
- Newly installed or enabled skills visible within one second on a warm running client, or on the next request when file watching is unavailable
- Warm local retrieval under 100 milliseconds at the 95th percentile on a representative workstation
- No selection of disabled skills or stale plugin versions
- Successful fallback to current behavior when the index cannot be used

The evaluation should report both routing quality and prompt tokens. Token reduction without routing recall is not a successful result.

## Rollout plan

### Phase 1: instrumentation

Expose diagnostic counts for active skills, rendered catalog tokens, shortened descriptions, and omitted entries. This would let users and the Codex team measure the actual problem before changing behavior.

### Phase 2: opt-in deferred discovery

Add a feature flag that enables the local index and candidate retrieval while retaining the current catalog as a fallback. Compare routing outcomes and prompt use through controlled evaluation and opt-in cohorts.

### Phase 3: client integration

Connect the `$` picker and explicit mentions to the local index. This is the step that preserves current usability while allowing leaf metadata to leave the prompt.

### Phase 4: threshold-based default

Use deferred discovery by default when the full skill catalog would consume a meaningful portion of its budget or require omission. Smaller catalogs can continue using the simpler current path if they fit comfortably in context.

## Alternatives considered

### Keep the current bounded catalog

This is simple and prevents unbounded growth. It does not solve omission or the recurring context cost at the budget limit.

### Shorten every description

Concise descriptions are good practice and delay the problem. They cannot solve it for an open-ended number of skills, and aggressive shortening can remove the trigger language needed for implicit routing.

### Disable skills globally or per project

Codex already supports per-skill enablement. This works when users know in advance which skills a project needs. It does not preserve universal availability across projects, and it adds maintenance overhead.

### Add a user-authored router skill

A router skill can search files after invocation, but it cannot remove the catalog that Codex injected before selecting the router. Hiding leaf skills in a separate directory can save tokens, but it also changes workflows for skill authors.

### Bundle many skills into domain meta-skills

An AWS, frontend, or document meta-skill can reduce catalog entries. This requires manual packaging, introduces another authoring convention, and does not generalize cleanly to unrelated or newly-introduced skills.

### Rely on prompt caching

Prompt caching can reduce repeated processing cost and latency. It does not reduce context occupancy, and exact cache behavior is separate from skill-discovery quality.

## Why this belongs in Codex

Only the Codex harness and client have all the information needed to solve the problem without changing user behavior:

- The active skill and plugin set
- Current scope and configuration
- The raw user prompt before model context is assembled
- The `$` picker and explicit mention resolver
- The ability to load a selected skill using existing trust rules
- The ability to fall back before a request is sent

A community plugin can prototype search and loading, but it cannot fully preserve native skill-picker behavior or guarantee that its router is invoked before catalog construction. A first-class implementation in Codex can preserve UX semantics while reducing prompt cost.

## Requested review

I would appreciate the Codex team's review of the following questions:

1. Is host-side deferred skill discovery already planned or implemented behind an existing capability?
2. Can the current deferred tool-search infrastructure be reused for skill metadata?
3. Would the team consider an opt-in experiment for installations whose catalog reaches the metadata budget?
4. If a first-party implementation is not planned, could Codex expose a supported pre-context skill-discovery hook and a client-side skill-index API so the community can implement it without losing native picker behavior?
5. Can Codex expose rendered skill-catalog token counts and omission diagnostics so users can measure the issue accurately?

## References

- [Build skills: progressive disclosure, catalog budget, invocation, locations, and enablement](https://developers.openai.com/codex/skills)
- [Codex configuration reference: `skills.config`](https://developers.openai.com/codex/config-reference)
- [Prompt caching: exact-prefix reuse, cached-token accounting, and rate-limit behavior](https://developers.openai.com/api/docs/guides/prompt-caching)
- [Open Agent Skills specification](https://agentskills.io/)

---

## V2 — Critical evaluation and recommendations

This v2 section is a critical engineering review of the proposal above. It summarizes strengths, identifies gaps and risks, and provides prioritized, actionable recommendations, tests, and rollout guardrails.

Summary verdict

The proposal is well-reasoned and addresses a real scaling problem with a practical architecture: keep a local index, run a lightweight retriever to return a small candidate set, and keep the model as the final decider. Proceed with a focused prototype (local index + lexical retriever + model-in-the-loop rerank) and the evaluation suite described in the original proposal, but tighten specs around index authority, invalidation, retrieval confidence, security, and observability before broad rollout.

Strengths

- Correct layering: discovery belongs at the harness/client because it has authoritative knowledge of installed and enabled skills.
- Minimal semantic change: SKILL.md loading semantics and model-in-the-loop judgment remain unchanged, minimizing authoring and compatibility risk.
- Practical retrieval strategy: start with lexical/fuzzy/BM25 and add optional embedding reranking when feasible.
- Safety-first: local-only index, no code execution during indexing, and a clear fallback to current catalog behavior.
- Good rollout plan: phased instrumentation, opt-in experiment, client integration, and threshold-based default.

Gaps, ambiguities, and technical risks

1. Index authority and activation state

Risk: indexing stale files or inactive plugin versions unless the index uses the plugin manager or installer as the authoritative source of activation state.

Recommendation: define and use a single authoritative activation source. Index entries should be tied to activation metadata produced by the plugin manager (version, enabled flag, install timestamp). The index should ignore cache directories unless explicitly marked active by the manager.

2. Invalidation and consistency

Risk: file-watching reliability varies across platforms and environments (containers, NFS, editors) which can produce stale or missed updates.

Recommendation: combine file watchers with periodic content-hash scans, support installer hooks for explicit invalidation, and make index updates atomic. Surface an `index_health` diagnostic (last_scan, last_update_reason, pending_changes) in telemetry and UI.

3. Duplicate and precedence semantics

Ambiguity: how to deterministically choose between multiple active skills with the same name.

Recommendation: define deterministic precedence rules (for example: repository-local > workspace > user > plugin > global), include source identity prominently in the picker, and provide an explicit disambiguation UI. Make precedence configurable by administrators.

4. Retrieval quality and semantic coverage

Risk: a purely lexical retriever (BM25/trigram) may miss semantically relevant skills, reducing implicit-routing recall.

Recommendation: include an embedding-based reranker where available. If embeddings are not available, implement aggressive widening (more candidates, category-based expansion) and visible uncertainty signals so the model can request expansion or the harness can fall back to the full catalog.

5. Confidence definition & thresholds

Ambiguity: the proposal calls for a minimum confidence threshold but doesn't specify measurable signals.

Recommendation: define confidence signals (normalized BM25 score, trigram match score, embedding cosine similarity) and a default threshold with telemetry. Allow dynamic widening when confidence is below threshold. Expose thresholds to experimentation.

6. Performance at scale and resource-constrained clients

Risk: initial indexing or scans could be slow on low-spec machines or with massive caches.

Recommendation: use incremental indexing, lazy indexing for low-priority directories, provide a low-resource mode that limits index size, and benchmark indexing cost. Use SQLite or LMDB with efficient indices and an option to snapshot the index for warm starts.

7. Security & privacy edge-cases

Missing detail: SKILL.md and metadata can include local paths or private identifiers; indexing and telemetry must avoid leaking sensitive data.

Recommendation: sanitize and normalize absolute paths in index entries, index only the advertised metadata fields, and make telemetry opt-in with aggregation and sampling safeguards.

8. Trust & approval semantics

Ambiguity: ensure implicitly discovered skills still enforce approval and trust rules prior to execution.

Recommendation: require a final authoritative check against the plugin manager/trust store before loading SKILL.md (hard guard). Mark index entries that require approval and prevent selection without explicit user consent when needed.

9. UX latency and failure modes

Risk: retrieval adds an extra step before model context assembly which can increase latency and variability.

Recommendation: measure end-to-end latency and set strict P95 targets (the proposal suggests P95 < 100 ms for retrieval). Provide a fast cached small-catalog fallback for visible UI flows (picker) and make retrieval asynchronous where possible.

10. Observability and telemetry

Missing detail: token-savings and routing-quality telemetry should be defined precisely.

Recommendation: implement telemetry events for: rendered_catalog_tokens, retrieved_candidate_count, retrieval_latency_ms, retrieval_confidence, fallback_count, routing_recall_topK, false_activation_count. Keep telemetry opt-in and privacy-preserving.

Operational semantics and implementation notes

- Index format: use a compact, versioned on-disk schema (SQLite or LMDB) with fields for qualified name, scope, source, plugin identifier/version, enablement flag, content-hash, timestamps, and optional embedding vector.
- Concurrency: use reader-friendly locking and atomic swaps for index updates to avoid blocking requests.
- Backwards compatibility: implement an `index_unavailable` flag that causes an exact fallback to current behavior. Ensure explicit `$skill` resolution always uses the authoritative index or falls back identically.
- Cross-repo resolution: define clear rules for repository-scoped discovery when CWD or repo context changes mid-session.

Testing and evaluation refinements

- Acceptance criteria additions: track precision and false-activation rate in addition to recall. Add a maximum allowable end-to-end latency regression budget for the retrieval+model-prep path.
- Datasets: create test sets with stale plugin caches, ambiguous prompts, mixed-language prompts, and short/long descriptions.
- A/B tests: run across client types (desktop, low-power laptops, remote-hosted sessions) to validate resource assumptions and experience parity.
- Index-update latency: measure cold and warm update latency after plugin install/enable/disable and ensure it meets the "visible within one second" target on warm clients.

Concrete prioritized roadmap (short)

1. Prototype (High): Build a local index (SQLite) and lexical retriever (exact, trigram, BM25) + optional embedding reranker. Provide APIs: search(query, limit), resolve_exact(name, scope), index.update(files...).
2. Activation authority (High): Integrate with the plugin manager as the authoritative activation source; ignore unactivated cache copies.
3. Confidence & widening (High): Define confidence signals, default thresholds, and widening strategies.
4. Invalidation (Medium): File watch + content-hash fallback + installer hooks + atomic swaps.
5. Security hardening (High): Path sanitization, no code execution, trust/approval checks before load.
6. Telemetry & diagnostics (Medium): rendered token counts, retrieval metrics, fallback rates, index health.
7. Opt-in experiment (Medium): Feature-flag rollout to developer cohort and collect routing / token metrics.

Failure modes and mitigations (summary)

- Missed skill (false negative): widen search and fall back to the full catalog; log and monitor.
- Stale/disabled skill surfaced: authoritative activation check at selection time; disallow execution until re-enabled.
- Index corruption: atomic swap fallback to previous index or full catalog; surface index health status.
- Privacy leak via telemetry: default to local-only telemetry; if sending, aggregate and sample.

Next steps I recommend you run now

- I can draft a concrete SQLite schema and a minimal API surface for the index. This will help the team estimate integration effort and build the prototype quickly.
- I can prepare an experiment telemetry plan (events, dashboards, thresholds) to validate acceptance criteria in Phase 1.
- I can generate a synthetic 200-skill dataset and run a quick token-savings simulation for the lexical retriever approach to show expected token reductions.

Which of these would you like me to do next?
