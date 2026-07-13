# 00 — Engineering Decision

## Decision

Codex MUST implement **Unified Adaptive Skill Routing (UASR)**.

UASR is an adaptive, authority-aware routing layer over the existing effective skill inventory. It
does not replace skill discovery, configuration, enablement, product gating, plugin activation,
filesystem ownership, or explicit invocation.

The implementation has four model-visible modes:

| Mode | Trigger | Model-visible skill material |
|---|---|---|
| Explicit | One or more exact skill references are present | Selected skill instructions or deferred read references |
| Lossless catalogue | Every implicitly invokable entry fits with complete routing metadata | Existing complete catalogue |
| Adaptive catalogue | Complete rendering would shorten any description or omit any entry | Bounded task-specific candidates plus recovery instruction |
| Degraded fallback | Router or snapshot construction fails | Existing bounded renderer plus diagnostic metric/warning |

The router MUST operate on one immutable effective snapshot for the current model step. Every entry
must remain bound to its owning authority and read mechanism.

## Why this is the correct direction

### It extends code already merged upstream

On 13 July 2026, Codex merged:

- a bounded `WeightedLexicalSkillSelector`;
- a `CheapSkillSelector` interface;
- a `ShadowSelectionExperiment`;
- metrics for selection duration, catalogue reduction, selected rank, and later observed invocation;
- a stable, default-enabled `skill_search` feature that runs the shadow experiment.

The next correct engineering step is to make that selector production-capable, fill its documented
gaps, and place it at the catalogue-rendering boundary. Creating another registry or unrelated
router would duplicate upstream work.

### It preserves the mature deterministic path

Codex already resolves explicit structured skill references and `$skill` mentions against the full
enabled inventory and reads selected instructions through the owner. UASR does not place a
probabilistic ranker in front of explicit selection.

### It solves both forms of lossy routing metadata

Description shortening can destroy trigger words and boundaries before any entry is omitted. The
official Codex documentation explicitly tells skill authors to front-load trigger words so that
shortened descriptions can still match. Therefore adaptive routing MUST activate when rendering
would shorten descriptions **or** omit entries, not only when omission occurs.

### It makes misses reversible

Automatic ranking alone creates a new silent-failure mode. A bounded `skills.search` tool gives the
model a way to reformulate the task after inspecting files or recognizing that the initial
candidates are inadequate.

### It supports newly installed skills without central registration

Every enabled skill automatically participates through the required `name` and `description`
metadata. Existing `short_description`, dependency, plugin, scope, and authority facts add
structured evidence where available. No hard-coded master list of skills is required.

## “Skills as rules” interpretation

The useful part of treating skills as rules is adopted, but not as a manually maintained global
taxonomy.

A skill description already declares a rule antecedent:

> use this skill when the task has these properties.

The harness compiles the current task into trusted routing evidence and evaluates that evidence
against all eligible skill metadata. For example:

```text
task evidence
  action=review
  artifact=pull_request
  provider=github
  concern=security
```

may raise GitHub review, code review, and security skills.

The model sees the resulting candidates, not the entire rule base.

Rules are used as **candidate evidence**, not as execution permission. Except for exact user
selection, no ordinary routing rule may force a skill to execute.

## Non-negotiable invariants

1. **Explicit means exact.** Exact structured references bypass ranking.
2. **No silent substitution.** A missing, disabled, or ambiguous explicit skill is reported; a
   similar skill is never substituted automatically.
3. **No authority laundering.** Host paths, executor resources, orchestrator resources, and custom
   resources remain owned and read by their source.
4. **No stale read.** Search and read operate on the same immutable step snapshot or fail.
5. **No broadening.** The router can only select from enabled entries allowed for implicit
   invocation in the current product and configuration.
6. **No silent body truncation.** Oversized instructions are exposed through bounded paginated reads.
7. **No unbounded context.** Candidate metadata, search output, instruction pages, warnings, and
   diagnostics all have hard caps.
8. **No duplicate catalogue injection.** One model step has one authoritative model-visible skill
   catalogue.
9. **No persistent parallel index.** Search documents are derived from the current snapshot.
10. **No raw-prompt telemetry.** Evaluation records bounded structural metrics, not user content.
11. **No mandatory taxonomy migration.** Existing valid skills continue to work without edits.
12. **No “MVP complete” state.** All required implementation units must land before the issue is
    considered solved.

## Rejected alternatives

### Increase the 2% budget

Rejected as the solution. It postpones the threshold and increases context occupancy. It remains a
useful experimental control.

### Omission-only recovery

Rejected. Shortening is itself lossy and can remove the “when to use” information on which implicit
matching depends.

### Rule-only category router

Rejected. Categories overlap, age poorly, and cannot automatically classify arbitrary newly
installed skills without new mandatory authoring metadata. It also creates a second availability
configuration surface.

### Model classification before every turn

Rejected. The harness already has the request. A separate model call adds latency, cost, another
failure point, and may classify incorrectly before file inspection.

### Search-tool-only discovery

Rejected as the sole path. It removes initial context but depends on the model realizing that an
unknown relevant skill exists. It is retained as recovery.

### Fixed top-five candidates

Rejected. Candidate descriptions vary in size and some tasks need several independent capabilities.
Selection is byte/token budgeted with a count ceiling, not fixed at five.

### Embedding/vector index

Rejected for this implementation. It adds a model/runtime dependency, persistence and invalidation
work, privacy questions, and cross-environment portability problems. The existing lexical selector
must first be completed and evaluated. The architecture leaves the selector interface replaceable.

### Persistent SQLite registry

Rejected. `SkillsService`, host snapshots, executor catalogues, and orchestrator caches already own
inventory and freshness. A second registry would create synchronization and authority bugs.

### Automatic source precedence for duplicate plain names

Rejected. An exact locator wins. A plain name that identifies multiple enabled skills is ambiguous
and must be disambiguated. Silently preferring executor, orchestrator, repository, or user scope can
execute a different workflow from the one the user intended.

## Complete change, reviewable commits

Codex repository guidance limits complex changes and encourages coherent review stages. The
implementation may be split into dependent pull requests, but that is a review strategy—not an MVP
strategy. No partial stack is the final solution.

## External evidence that cannot be fabricated

Only OpenAI maintainers can inspect fleet-wide shadow metrics. This specification resolves the
architecture and behavior; it does not invent production recall figures. Before active cutover,
maintainers MUST confirm the verification gates in `11-verification-and-test-plan.md` using the
already-enabled shadow telemetry.
