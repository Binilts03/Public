# 03 — System Architecture

## Architectural overview

```text
                   existing discovery and policy owners
       ┌────────────────┬──────────────────┬───────────────────┐
       │ Host snapshot  │ Ready executor   │ Orchestrator/custom│
       │ SkillsService  │ catalogues       │ provider catalogues│
       └───────┬────────┴─────────┬────────┴──────────┬────────┘
               │                  │                   │
               └──────────────┬───┴───────────────────┘
                              ▼
                  SkillRoutingSnapshotBuilder
                    - filter and deduplicate
                    - preserve authority/source
                    - bind read routes
                    - assign generation
                              │
                              ▼
                  immutable SkillRoutingSnapshot
                    ├─ explicit-available entries
                    ├─ implicit-eligible entries
                    ├─ read routes
                    └─ render/search documents
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
       explicit reference resolver    full-catalog render probe
                │                           │
                │                   lossless│lossy
                │                         ┌─┴───────────────┐
                │                         ▼                 ▼
                │                 full catalogue    RoutingEvidenceBuilder
                │                                           │
                │                                           ▼
                │                                AdaptiveSkillSelector
                │                                 lexical + trusted boosts
                │                                           │
                │                                           ▼
                │                                  candidate allocator
                │                                           │
                └──────────────────────┬────────────────────┘
                                       ▼
                          one model-visible skill section
                                       │
                         ┌─────────────┴─────────────┐
                         ▼                           ▼
                 inline instructions          skills.search/read
                 or deferred refs              same step snapshot
```

## Component responsibilities

### Existing inventory owners

Inventory owners remain authoritative.

#### Host

`SkillsService` discovers and caches host skills. `HostSkillsSnapshot` owns the exact filesystem
mapping used to read each host skill. The router consumes the snapshot; it does not reproduce
discovery.

#### Executor

The selected-executor provider lists skills only from ready selected capability roots. The snapshot
must retain the environment/resource binding necessary to read those skills through the captured
executor authority.

#### Orchestrator

The orchestrator provider lists and reads hosted skill resources through the current MCP resource
generation. The existing per-generation catalogue and resource caches remain the owner.

#### Custom

A custom provider must satisfy the same list/read authority contract. UASR does not assume a local
path.

### `SkillRoutingSnapshotBuilder`

New authority-neutral builder in the skills extension.

Responsibilities:

1. accept the current host snapshot and provider catalogues;
2. apply enabled and prompt visibility state already calculated by owners;
3. reject malformed or conflicting source identities;
4. deduplicate only identical authority-plus-package entries;
5. preserve same-name entries from different identities;
6. project the minimal routing metadata required by the selector;
7. bind each entry to a read route;
8. compute a stable process-local generation;
9. produce immutable vectors and lookup indexes;
10. produce bounded warnings.

The builder MUST NOT:

- scan the filesystem;
- read `SKILL.md` bodies;
- execute scripts;
- start dependencies;
- resolve ambiguous names;
- merge semantically similar skills;
- apply a new enablement policy.

### `SkillRoutingSnapshot`

Proposed shape:

```rust
pub(crate) struct SkillRoutingSnapshot {
    generation: SkillRoutingGeneration,
    entries: Arc<[RoutingSkillEntry]>,
    by_identity: Arc<HashMap<SkillIdentity, usize>>,
    by_exact_name: Arc<HashMap<String, SmallVec<[usize; 2]>>>,
    read_routes: Arc<HashMap<SkillIdentity, SkillReadRoute>>,
    host_snapshot: Option<Arc<HostSkillsSnapshot>>,
}
```

The type is immutable after construction.

It contains two logical views:

```rust
fn explicit_entries(&self) -> impl Iterator<Item = &RoutingSkillEntry>;
fn implicit_entries(&self) -> impl Iterator<Item = &RoutingSkillEntry>;
```

An enabled skill with `allow_implicit_invocation=false` appears only in the explicit view.

### `RoutingEvidenceBuilder`

Produces a bounded `RoutingEvidence` object from:

- current `UserInput`;
- exact structured mentions;
- bounded previous user text;
- skills used in the immediately preceding task;
- current collaboration/review mode;
- named attachments and MIME types;
- URLs and recognized URL path types;
- file names and extensions explicitly supplied in the turn;
- provider/tool dependency facts;
- current repository scope and selected environment identifiers where already available.

It MUST NOT read arbitrary repository files or make a model call.

### `AdaptiveSkillSelector`

The current `WeightedLexicalSkillSelector` becomes one scoring component rather than being discarded.

The active selector:

1. creates one search document per implicitly eligible entry;
2. runs the weighted lexical baseline;
3. calculates trusted evidence boosts;
4. applies bounded continuity and scope tie-breakers;
5. rejects zero-evidence candidates;
6. sorts deterministically;
7. passes ranked candidates to the allocator.

The selector returns identities, scores, and low-cardinality reason flags for diagnostics. It does not
load bodies or decide execution.

### Candidate allocator

The allocator renders complete candidate lines in rank order into the candidate budget.

Algorithm:

1. reserve space for the stable adaptive-discovery instruction;
2. include all exact-name candidates caused by non-explicit exact text evidence;
3. include ranked entries while the complete line fits;
4. stop at 12 entries;
5. if fewer than four candidates fit and at least four positive-scoring candidates exist, rerender
   the top candidates using the mature fair description allocator with a 256-character target floor;
6. never omit name, authority/access kind, or opaque handle;
7. report how many positive-scoring candidates were not shown.

The candidate list is not a permission list. Search can recover entries outside it.

### Full-catalog render probe

The probe uses the same canonical renderer intended for final model visibility.

It returns:

```rust
pub(crate) enum SkillVisibilityMode {
    Full(AvailableSkills),
    Adaptive {
        full_report: SkillRenderReport,
        candidates: AvailableSkills,
    },
    Degraded {
        fallback: Option<AvailableSkills>,
        reason: RoutingFailureKind,
    },
}
```

The adaptive condition is any description shortening or omission.

### Explicit resolver

The explicit resolver operates over `explicit_entries()` before adaptive ranking.

Resolution order:

1. exact structured authority/package/resource identity;
2. exact structured host path;
3. exact `$qualified-name`;
4. unambiguous exact `$name`.

Natural-language text without a skill mention is not elevated to deterministic explicit selection.
Exact names in such text receive a strong implicit score.

### Search and read tools

`skills.search` searches the step snapshot.

`skills.read` reads a selected resource through its bound route and returns a bounded page.

Both tools validate the generation/identity. They do not accept an ambient path and then infer an
authority.

### Step state

A model step needs exactly one snapshot. The recommended state owner is the skills extension:

```rust
pub(crate) struct SkillsStepState {
    snapshot: Arc<SkillRoutingSnapshot>,
    routing_evidence: Arc<RoutingEvidence>,
    visible_identities: HashSet<SkillIdentity>,
    recovery_budget: Mutex<RecoveryBudget>,
    explicitly_selected: Arc<[SkillIdentity]>,
}
```

Because the current `ToolContributor` API exposes session and thread stores but not the turn store,
the implementation has two options:

1. change `ToolContributor::tools` to receive `turn_store`; or
2. maintain an active-turn snapshot map in `SkillsThreadState`, keyed by turn ID.

The selected design is **option 2** for the current baseline because it changes fewer unrelated
extensions. It is safe only with the following rules:

- key by exact turn ID;
- store an `Arc<SkillsStepState>`;
- replace atomically before each model request;
- tool calls resolve the exact turn ID supplied by the host;
- remove state on turn stop/abort/error;
- cap retained entries to active turns;
- reject missing or generation-mismatched handles;
- do not fall back to the latest snapshot from another turn.

If upstream changes the tool-contributor API before implementation, use direct turn-store access
instead and remove the map. The functional contract is the same.

## Model-step lifecycle

### First step of a turn

```text
1. Host creates turn stores and captures HostSkillsSnapshot.
2. World-state contributors resolve ready executor roots.
3. Skills extension obtains host, executor, and orchestrator catalogues.
4. Snapshot builder creates one immutable SkillRoutingSnapshot.
5. Explicit references resolve against the explicit view.
6. RoutingEvidenceBuilder creates evidence.
7. Full renderer is probed.
8. Lossless -> full catalogue.
   Lossy    -> candidate catalogue + recovery instruction.
9. Explicit skill bodies are inlined or represented by deferred references.
10. Step state is published before the model request.
11. Model request is sent.
12. Any skills.search/read call resolves against this exact step state.
```

### Later step in the same turn

A later model request can occur after tool calls or environment changes.

```text
1. Re-resolve ready dynamic sources.
2. Build a new immutable snapshot if source generation/availability changed.
3. Preserve the original user routing evidence and add bounded facts explicitly learned by the
   harness, not arbitrary model output.
4. Recompute candidate visibility.
5. Publish a replacement world-state/candidate section.
6. Replace active step state atomically.
```

An old tool handle may not be used against a different generation.

## One authoritative model-visible catalogue

The implementation must remove duplicate ownership.

At the pinned baseline:

- host metadata can be injected through turn input;
- executor metadata can be projected through world state;
- orchestrator skills can be exposed through tools/thread context;
- legacy core rendering still exists.

The completed architecture chooses a single authoritative `AvailableSkills` fragment per model step.
Other paths may still expose picker/admin inventory but MUST NOT inject a second catalogue for the
same step.

The preferred destination is the skills extension because:

- it already owns the source-neutral `SkillCatalog`;
- it owns host/executor/orchestrator providers;
- it owns `skills.list`, `skills.read`, and the shadow selector;
- repository guidance discourages adding new concepts to `codex-core`.

The mature core fair renderer should be extracted or generalized for reuse rather than duplicated.

## Data flow for newly installed skills

```text
installation / file change / plugin lifecycle event
                    │
                    ▼
        existing owner invalidates generation/cache
                    │
        current step remains immutable
                    │
                    ▼
           next snapshot construction
                    │
                    ▼
 new metadata automatically becomes a routing document
                    │
        ┌───────────┴────────────┐
        ▼                        ▼
 lexical description match   structured existing evidence
                             (dependency/plugin/scope)
```

No central skill-category edit is required.

## Data flow for explicit X, Y, and Z

```text
structured/$ references -> exact resolver -> validate all
                                      │
                    any required failure?
                         yes ─────────┴── fail closed with diagnostic
                         no
                                      ▼
                         preserve X,Y,Z user order
                                      ▼
                 inline complete bodies within aggregate budget
                 + deferred references for remaining/oversized bodies
                                      ▼
                 suppress implicit additions unless user permitted them
```

## Prompt placement

Stable usage instructions belong in stable developer context.

The task-specific candidate catalogue belongs in turn/world-state context after stable prefixes.
This preserves prompt-cache reuse for stable content; exact-prefix caching requires changing content
to appear after the reusable prefix.

Candidate fragments are replacement state, not append-only permanent conversation history.

## Concurrency model

- `SkillRoutingSnapshot` is immutable and `Arc` shared.
- Recovery counters use a small mutex or atomics in step state.
- Snapshot replacement is atomic at the thread-state map.
- Search itself is read-only and side-effect free except for budget consumption and metrics.
- Reads may be asynchronous and source-specific.
- Two concurrent tool calls for the same page are allowed; provider/resource cache deduplicates where
  available.
- Turn cleanup cannot drop a snapshot still held by an in-flight tool call because the executor holds
  an `Arc`.

## Complexity

Let `N` be implicit entries and `T` normalized query terms.

- evidence extraction: bounded by query and attachment limits;
- selector: `O(N*T)` under current lexical scoring;
- sorting: `O(M log M)` where `M` is positive-score entries;
- allocation: `O(K)` where `K` is ranked results examined;
- memory: `O(N)` metadata references for the snapshot.

At the 10,000-entry safety cap and 64-term cap this remains bounded. Implementations may use a
top-k heap to avoid sorting all positive entries, but deterministic output must remain identical.
