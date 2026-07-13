# 08 — Model Context, Prompt Assembly, and Skill Body Loading

## Context objective

The full effective inventory remains host-side. Model context contains only:

- stable skill-usage guidance;
- either a lossless full catalogue or an adaptive candidate catalogue;
- exact selected skill instructions that fit;
- deferred instruction references;
- bounded recovery results/pages requested by the model.

Context reduction is not context elimination. Candidate metadata and selected instructions still
consume tokens.

## Stable versus variable prompt material

Prompt caching depends on exact prefix matches. Therefore:

### Stable prefix

- generic skill usage policy;
- stable `skills.search` and `skills.read` tool definitions;
- system/developer rules that do not depend on the current task.

### Variable suffix/turn state

- task-specific candidate catalogue;
- current source availability;
- explicit selected instruction fragments;
- recovery outputs;
- read pages.

Do not place a changing candidate list before otherwise stable long instructions.

## Full catalogue mode

Use when canonical rendering produces:

```text
omitted_count == 0
AND truncated_description_chars == 0
```

The existing full-catalogue semantics remain:

- every implicit entry is visible;
- complete routing description is present;
- model may select a skill and read it;
- no recovery instruction is required, though the search tool may remain registered if needed for
  deferred reads.

## Adaptive mode

Use when the full render would be lossy.

Model-visible section:

```text
<skills_instructions mode="adaptive">
  <usage>stable recovery guidance</usage>
  <candidates>
    ...bounded candidate lines...
  </candidates>
</skills_instructions>
```

Use the repository's contextual-fragment abstraction rather than raw string injection.

The fragment is step/turn contextual state. It must not be permanently appended to history as an
ordinary user message.

## Replacement semantics

When candidate state changes between model steps:

- the new world-state/contextual fragment replaces the prior active candidate state;
- conversation history is not rewritten;
- prior tool outputs remain historical facts but are not treated as current inventory;
- the active `SkillsStepState` points only to the new snapshot.

This follows Codex's “no history rewrite” rule while preventing catalogue accumulation.

## Explicit instruction placement

Selected skill instructions are placed after the stable usage policy and before task execution.

Each fragment identifies:

- display name;
- authority/source label;
- package/resource identity or safe locator;
- complete inline contents, or a deferred read handle;
- explicit versus implicit invocation;
- user order for explicit sets.

## Inline instruction policy

Inline only complete content.

```text
per item <= 8,000 UTF-8 bytes
total <= 32,000 UTF-8 bytes
count <= 8
```

If any limit would be exceeded, use a deferred reference for that skill. Do not truncate and append
an ellipsis.

The current extension behavior that truncates a selected main prompt at 8,000 bytes must be replaced
for the completed solution.

## Deferred instruction policy

A deferred reference says:

- this skill was selected;
- its complete main instructions are not inline;
- the model must call `skills.read`;
- it must continue until `complete=true`;
- it must not claim compliance before completion.

Example conceptual fragment:

```text
<selected_skill name="large-review" invocation="explicit">
  <source authority="host" package="opaque" generation="42" />
  <instruction>
    Read this skill through skills.read before acting. Continue with next_cursor until complete=true.
  </instruction>
</selected_skill>
```

## Paginated reads

### Page construction

- read complete source content through the owner;
- enforce 1 MiB maximum;
- cache content in the active step where existing provider caches do not;
- return pages no larger than 8,000 bytes;
- cut only at UTF-8 boundaries;
- preserve exact byte order;
- return `next_cursor`;
- mark final page `complete=true`.

### Markdown boundaries

Do not silently alter or summarize the body to create visually neat pages. Pages may split Markdown
blocks. The model receives exact sequential text.

An implementation MAY prefer the nearest preceding newline within a small bounded window, provided:

- no content is skipped;
- no content is duplicated;
- cursor offsets remain exact and tested.

### References inside `SKILL.md`

This design covers the main prompt. Existing skill instructions may direct the model to read
reference files or scripts. Those resources continue through existing filesystem/provider access and
approval boundaries. `skills.read` must not automatically crawl all references.

## Multiple deferred skills

The model must complete all required reads before applying the combined workflow.

The user order controls the recommended read order. Parallel reads are permitted when tool parallelism
and source safety allow, but instruction conflict cannot be evaluated until all required bodies are
available.

## Search outputs in context

Search output is bounded external context. It includes metadata only.

It does not make a returned skill active. The model must select/read it.

Search outputs from earlier steps remain historical tool output, but handles are generation-bound.
Attempting to read one after the active generation changes returns stale-handle error.

## Candidate descriptions

Candidate descriptions are routing data, not instructions. The model must not execute commands found
inside descriptions. Stable usage guidance should say that instructions come only from a selected
main prompt.

## Candidate accumulation

Hard rule:

- initial candidates: maximum 12 / 8,000 bytes;
- recovery: maximum 16 unique / 8,000 cumulative bytes / two calls per step;
- no automatic listing of the complete remaining catalogue;
- a second refined search excludes already returned identities by default.

## Model chooses no skill

This is valid. The candidate catalogue is advisory. No skill body is loaded unless explicitly
selected or read.

## Model reads several implicit skills

Allowed when the task genuinely needs them.

Each read is recorded as an implicit invocation and is subject to body/page limits. The model should
coordinate them using the same conflict rule as explicit multi-skill selection, but implicit order is
the order of selection/read.

## Context compaction

### Before compaction

Candidate fragments are active contextual state.

### Compaction output

The compactor should preserve:

- material task state;
- explicit selections still required;
- material completed skill-guided work;
- unresolved deferred-read obligations.

It should not embed:

- the complete candidate catalogue;
- raw search result catalogues;
- stale handles;
- recovery counters.

### After compaction

Recompute candidate state from current sources and the active user task. If an explicit deferred
skill remains required, issue a fresh handle or preserve a valid identity and rebind it to the new
generation with explicit validation.

## Resume and replay

Persisted history may contain old skill instruction fragments and tool outputs.

On resume:

- do not trust old process-local generation values;
- do not replay old candidate lists as current;
- reconstruct active explicit requirements from structured user input/history;
- build a new snapshot;
- re-read selected instructions if needed;
- keep ordinary completed outputs in history.

## Fork

A fork may inherit past instruction content as conversation history, but it obtains a new active
snapshot and candidate catalogue. It does not inherit recovery budgets or active handles.

## Prompt cache behavior

Prompt caching can reduce repeated processing cost/latency for exact prefixes. It does not remove
tokens from the logical context and does not make an oversized catalogue harmless.

UASR improves cache behavior by:

- leaving stable guidance at the prefix;
- putting task-specific candidates later;
- avoiding unnecessary changes to stable tool definitions;
- keeping candidate format stable;
- not adding one unique tool schema per skill.

## Warnings

Warnings are model-visible only when they affect task execution, for example:

- required explicit skill unavailable;
- selected body cannot be read;
- recovery budget exhausted;
- catalogue incomplete for an active source.

Operational warnings such as “shadow selector took 3 ms” remain telemetry/debug data.

Warnings:

- maximum four per result/step;
- maximum 256 bytes each;
- deduplicated by error category/source;
- no raw paths or secrets unless an existing explicit diagnostic contract requires them.

## Legacy fallback

If adaptive selection fails:

1. render the existing bounded catalogue;
2. mark the step as degraded in telemetry;
3. show the existing omission/truncation warning;
4. keep explicit resolution functional;
5. keep uniform read functional for exact selections if snapshot construction succeeded;
6. never send both fallback and adaptive catalogues.

## Context tests

Required assertions:

- stable guidance precedes variable candidates;
- candidate fragment is bounded by UTF-8 bytes;
- full mode contains every entry and full descriptions;
- adaptive mode triggers on first shortened character;
- adaptive mode triggers on first omission;
- no duplicate host catalogue from core and extension;
- executor world state and host candidates are one authoritative section;
- explicit inline body is complete;
- oversized body produces reference, not truncated prefix;
- pagination reconstructs exact original bytes;
- compaction does not retain old candidate state;
- resume rejects old cursors;
- prompt snapshots remain deterministic;
- no model-visible item exceeds repository limit.
