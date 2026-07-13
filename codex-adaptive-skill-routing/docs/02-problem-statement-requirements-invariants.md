# 02 — Problem Statement, Requirements, and Invariants

## Problem statement

Codex must preserve reliable implicit and explicit skill use as the effective skill catalogue grows,
without placing the complete catalogue in model context when rendering it would be lossy.

The problem has five coupled parts:

1. **Model visibility:** a relevant skill cannot be chosen implicitly if its routing metadata is
   absent or no longer meaningful after shortening.
2. **Authority:** the same logical skill name may exist on the host, a selected executor, an
   orchestrator, or a future custom source; metadata and reads must remain bound.
3. **Freshness:** the effective catalogue may change between model steps while a step itself requires
   an immutable view.
4. **Recovery:** a local ranker can miss; the miss must not become permanent.
5. **Context safety:** catalogue metadata, selected instructions, and search output must all remain
   bounded and compatible with prompt caching, compaction, resume, and fork.

## Scope

The implementation covers:

- Codex CLI, IDE, desktop/app-server paths that use the shared Rust skill infrastructure;
- host, selected-executor, orchestrator, and custom authority shapes;
- explicit and implicit invocation;
- lossless and lossy catalogue rendering;
- task-specific routing evidence;
- initial candidate selection;
- model-triggered recovery;
- complete selected-skill reads;
- installation, update, enablement, disablement, removal, plugin refresh, environment availability,
  resume, fork, compaction, and source failure;
- telemetry and verification;
- compatibility with current valid skills.

It does not create a general workflow marketplace, user segmentation, billing system, SaaS control
plane, or learned recommendation service.

## Terminology

| Term | Definition |
|---|---|
| Effective inventory | Skills that discovery and configuration make available before model-visibility filtering |
| Explicitly available | Enabled skills that may be selected by exact user reference, including `allow_implicit_invocation=false` |
| Implicitly eligible | Enabled, product-allowed, prompt-visible skills allowed for implicit invocation |
| Full catalogue | Model-visible metadata for every implicitly eligible skill |
| Lossless render | Every eligible entry is present and its chosen routing description is complete |
| Lossy render | At least one description is shortened or at least one entry is omitted |
| Routing evidence | Bounded facts derived from the current request and trusted runtime state |
| Candidate catalogue | Bounded ranked subset exposed for the current task |
| Recovery search | Model-initiated search over the same effective step snapshot |
| Step snapshot | Immutable catalogue and source bindings used by one model request and its immediate tool calls |
| Skill handle | Opaque authority/package/resource identity; not a path to be reinterpreted by another source |
| Inline instruction | Complete selected skill content included directly in model input |
| Deferred instruction | Selected skill content read through bounded `skills.read` pages |

## Functional requirements

### Inventory and snapshot

**REQ-INV-001**  
The router MUST consume the existing effective inventory. It MUST NOT scan skill directories or
plugin caches independently.

**REQ-INV-002**  
Every model step MUST have one immutable `SkillRoutingSnapshot`.

**REQ-INV-003**  
The snapshot MUST include every currently available authority and MUST bind every entry to the
source that listed it.

**REQ-INV-004**  
Enabled, product, configuration, and `allow_implicit_invocation` policies MUST be applied before
implicit ranking.

**REQ-INV-005**  
Explicit selection MUST use enabled entries even when implicit invocation is disabled.

**REQ-INV-006**  
A snapshot MUST have a stable process-local generation identity used to reject stale search/read
handles.

### Rendering mode

**REQ-MODE-001**  
Codex MUST compute the render report before choosing the model-visible mode.

**REQ-MODE-002**  
If every implicit entry fits with a complete routing description, Codex MUST preserve the full
catalogue behavior.

**REQ-MODE-003**  
If any routing description would be shortened or any entry omitted, Codex MUST use adaptive
candidate routing.

**REQ-MODE-004**  
A router failure MUST fall back to the existing bounded renderer for that step and emit a bounded
diagnostic and metric.

### Explicit invocation

**REQ-EXP-001**  
Structured skill inputs, `$name`, and exact opaque locators MUST be resolved before implicit
selection.

**REQ-EXP-002**  
Exact explicit selections MUST be preserved in user order and deduplicated by authority plus
package identity.

**REQ-EXP-003**  
If an explicit reference is missing, disabled, unavailable, stale, or ambiguous, Codex MUST NOT
silently substitute another skill.

**REQ-EXP-004**  
A required explicit selection failure MUST prevent task execution until corrected, unless the user
explicitly requested best-effort continuation.

**REQ-EXP-005**  
Implicit supplementation MUST be disabled when the user provides an exact closed set, except for
required dependencies and higher-priority system behavior.

**REQ-EXP-006**  
When the user explicitly permits additional relevant skills, implicit routing MAY supplement the
explicit set.

### Implicit selection

**REQ-IMP-001**  
The selector MUST rank all implicitly eligible entries in the step snapshot, subject only to a
documented global safety cap.

**REQ-IMP-002**  
The current weighted lexical selector MUST remain the baseline scoring component.

**REQ-IMP-003**  
Trusted routing evidence MUST augment ranking without forcing ordinary skill execution.

**REQ-IMP-004**  
The router MUST support exact name, phrase, normalized token, prefix-related, artifact, URL,
dependency, scope, plugin/source, and bounded continuity evidence.

**REQ-IMP-005**  
Ranking MUST be deterministic for the same snapshot and evidence.

**REQ-IMP-006**  
The candidate catalogue MUST be budgeted by rendered size and capped by count.

**REQ-IMP-007**  
The selected subset MUST retain authority and opaque resource identity.

**REQ-IMP-008**  
A newly installed valid skill MUST become automatically eligible after the existing inventory
refresh, without a central registration edit.

### Recovery

**REQ-REC-001**  
Adaptive mode MUST expose a `skills.search` recovery tool.

**REQ-REC-002**  
Search MUST operate over the same step snapshot, not the filesystem and not a later refreshed
catalogue.

**REQ-REC-003**  
Search MUST exclude entries already presented unless the model explicitly asks to include them.

**REQ-REC-004**  
Search calls and cumulative result bytes/count MUST have hard per-step limits.

**REQ-REC-005**  
Search results MUST be read through the authority that returned them.

**REQ-REC-006**  
No-match search is a valid bounded result and MUST NOT trigger automatic execution or unbounded
fallback listing.

### Instruction loading

**REQ-READ-001**  
Selected instructions MUST never be silently truncated.

**REQ-READ-002**  
Complete instructions that fit the inline budget MAY be injected directly.

**REQ-READ-003**  
Oversized or cumulative-overflow instructions MUST be represented by a deferred read reference.

**REQ-READ-004**  
`skills.read` MUST support bounded pagination at UTF-8 boundaries and MUST indicate completion.

**REQ-READ-005**  
`skills.read` MUST support every authority represented in search results.

**REQ-READ-006**  
The model MUST be instructed to complete required reads before acting under that skill.

### Lifecycle

**REQ-LIFE-001**  
Changes during a model step MUST NOT mutate that step's snapshot.

**REQ-LIFE-002**  
The next step MUST observe a successfully refreshed host/plugin/orchestrator/executor generation.

**REQ-LIFE-003**  
A source that becomes unavailable MUST be removed from the next step projection without invalidating
the completed previous step.

**REQ-LIFE-004**  
Resume and fork MUST reconstruct routing from current effective sources, while preserving explicit
user references and conversation history semantics.

**REQ-LIFE-005**  
Compaction MUST NOT permanently preserve obsolete candidate catalogues as active routing state.

### Observability

**REQ-OBS-001**  
The implementation MUST retain shadow comparison until active behavior is verified.

**REQ-OBS-002**  
Metrics MUST distinguish explicit, full-catalogue, adaptive-initial, adaptive-recovery, and degraded
fallback paths.

**REQ-OBS-003**  
Invocation ground truth MUST include host, executor, orchestrator, and custom read/injection paths.

**REQ-OBS-004**  
Telemetry MUST NOT contain raw user prompts, skill bodies, descriptions, paths, package handles, or
unbounded high-cardinality names.

### Compatibility

**REQ-COMP-001**  
Existing valid skills need no authoring changes.

**REQ-COMP-002**  
The picker and app-server full inventory APIs MUST continue to expose enabled skills according to
their existing contracts.

**REQ-COMP-003**  
`allow_implicit_invocation=false` MUST continue to preserve explicit invocation.

**REQ-COMP-004**  
Exact structured inputs and persisted rollouts MUST remain compatible.

**REQ-COMP-005**  
When adaptive routing is disabled or rolled back, the legacy bounded catalogue MUST remain usable.

## Non-functional requirements

**REQ-NF-001 — Boundedness**  
Every model-visible fragment and tool output has a hard byte or token cap. No item may violate the
repository's model-context limits.

**REQ-NF-002 — Latency**  
Local ranking must be synchronous, deterministic, and cheap enough for every affected step. It must
not perform network calls, file reads, script execution, embedding inference, or dependency startup.

**REQ-NF-003 — Memory**  
Search documents are derived from immutable snapshots and released with them. No duplicate
persistent index is permitted.

**REQ-NF-004 — Portability**  
Routing works when the orchestrator has no direct filesystem and when a skill is owned by a remote
executor or hosted provider.

**REQ-NF-005 — Reviewability**  
Complex logic lives outside `codex-core` where possible, in modules under the repository's preferred
size limits.

**REQ-NF-006 — Determinism**  
Ties use documented stable keys. Filesystem enumeration order, hash-map iteration, and arrival order
must not change results.

**REQ-NF-007 — Privacy**  
The selector processes prompt text in memory but does not persist it or emit it as telemetry.

## Hard limits

These limits are part of the implementation contract and may be changed only through a reviewed
constant/config change with tests:

| Limit | Value |
|---|---:|
| Maximum routing query bytes | 16 KiB |
| Maximum normalized query terms | 64 |
| Maximum searchable skill entries | 10,000 |
| Maximum initial candidate entries | 12 |
| Maximum initial candidate metadata | 8,000 UTF-8 bytes and never above the current legacy budget |
| Minimum target candidates when matches exist | 4, unless fewer eligible matches exist |
| Default recovery results | 8 |
| Maximum recovery results per call | 16 |
| Maximum recovery calls per model step | 2 |
| Maximum unique recovery results per step | 16 |
| Maximum cumulative recovery output | 8,000 UTF-8 bytes |
| Maximum inline skill instruction bytes per item | 8,000 |
| Maximum aggregate inline skill instruction bytes per step | 32,000 |
| Maximum directly inline skill count | 8 |
| `skills.read` page size | maximum 8,000 UTF-8 bytes |
| Maximum readable bytes for one skill main prompt | 1 MiB |
| Maximum bounded prior-user routing context | 2,048 UTF-8 bytes |
| Maximum diagnostic warnings in a tool result | 4 |
| Maximum warning length | 256 UTF-8 bytes |

The 10,000-entry safety cap is not permission to take the first 10,000 entries. If exceeded, implicit
adaptive routing fails closed with a diagnostic; exact explicit resolution remains available.

## Precedence

From highest to lowest:

1. system and platform safety/policy;
2. effective product, admin, configuration, and enablement policy;
3. exact explicit user skill references;
4. the user's task requirements and requested ordering;
5. skill instructions;
6. implicit routing evidence and ranking;
7. general model preference.

Ranking never overrides a higher level.

## Success condition

The issue is solved only when the implementation satisfies every requirement mapped in
`13-requirements-traceability.md` and the full verification plan passes. A feature flag may exist for
safe cutover and rollback, but feature-flagged partial behavior is not the definition of completion.
