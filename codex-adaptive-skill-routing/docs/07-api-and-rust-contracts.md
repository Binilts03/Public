# 07 — API and Rust Contracts

## Placement

New routing logic belongs in `codex-rs/ext/skills`, with reusable bounded rendering primitives in
`codex-rs/core-skills` only where they already exist and can be generalized without adding routing
policy to `codex-core`.

Avoid a new crate unless implementation size or dependency direction makes `ext/skills` violate the
repository's module-size rules.

## Catalogue metadata changes

Current `SkillCatalogEntry` lacks host scope and plugin identity even though `SkillMetadata` has
them. Add optional routing metadata without making local paths universal:

```rust
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SkillRoutingMetadata {
    pub scope: Option<SkillScope>,
    pub plugin_id: Option<String>,
    pub plugin_display_name: Option<String>,
}
```

Add to `SkillCatalogEntry`:

```rust
pub routing: SkillRoutingMetadata,
```

Providers populate only facts they own.

Do not add a manually authored mandatory category field.

## Identity

```rust
#[derive(Clone, Debug, Eq, Hash, PartialEq)]
pub struct SkillIdentity {
    pub authority: SkillAuthority,
    pub package: SkillPackageId,
}
```

`SkillResourceId` remains the main-prompt/resource identity.

## Bound source

Current providers can list and read, but a model-step snapshot must bind an entry to the exact source
generation.

```rust
pub(crate) trait BoundSkillSource: Send + Sync {
    fn generation(&self) -> SkillSourceGeneration;
    fn authority(&self) -> &SkillAuthority;

    fn read(
        &self,
        request: SkillReadRequest,
    ) -> impl Future<Output = SkillProviderResult<SkillReadResult>> + Send;
}
```

Follow repository guidance: newly added traits need role/implementation doc comments and explicit
`Send` future bounds; do not use `async_trait`.

A source may internally delegate to existing `SkillProvider::read`.

## Routing entry

```rust
pub(crate) struct RoutingSkillEntry {
    pub identity: SkillIdentity,
    pub name: String,
    pub description: String,
    pub short_description: Option<String>,
    pub main_prompt: SkillResourceId,
    pub display_path: Option<String>,
    pub dependencies: Option<SkillDependencies>,
    pub routing: SkillRoutingMetadata,
    pub enabled: bool,
    pub prompt_visible: bool,
    pub source_generation: SkillSourceGeneration,
}
```

## Search document

Extend the current document:

```rust
pub(crate) struct SkillSelectionDocument<'a> {
    pub id: usize,
    pub name: &'a str,
    pub short_description: Option<&'a str>,
    pub description: &'a str,
    pub plugin_id: Option<&'a str>,
    pub plugin_display_name: Option<&'a str>,
    pub dependency_values: &'a [&'a str],
    pub dependency_descriptions: &'a [&'a str],
    pub scope: Option<SkillScope>,
    pub authority_kind: &'a SkillSourceKind,
}
```

If borrowed nested vectors make the API awkward, use a pre-normalized owned `RoutingDocument` stored
in the snapshot. Prefer readable code over lifetime complexity.

## Selector contract

Retain `CheapSkillSelector` for shadow comparability, and add an active selector contract:

```rust
pub(crate) struct SkillSelectionRequest<'a> {
    pub evidence: &'a RoutingEvidence,
    pub documents: &'a [RoutingDocument],
    pub max_ranked: usize,
}

pub(crate) struct RankedSkillCandidate {
    pub id: usize,
    pub score: u32,
    pub matched_current_terms: u16,
    pub matched_fact_count: u16,
    pub reasons: SkillMatchReasonFlags,
}

pub(crate) trait SkillSelector: Send + Sync {
    fn method(&self) -> &'static str;

    fn rank(
        &self,
        request: SkillSelectionRequest<'_>,
    ) -> SkillSelectionResult;
}
```

`SkillSelectionResult` reports query/document truncation and catalogue-cap status.

## Visibility mode

```rust
pub(crate) enum SkillCatalogueMode {
    Full {
        available: AvailableSkills,
    },
    Adaptive {
        candidates: AvailableSkills,
        visible: Arc<[SkillIdentity]>,
        omitted_positive_matches: usize,
    },
    ExplicitOnly,
    Degraded {
        fallback: Option<AvailableSkills>,
        reason: SkillRoutingFailure,
    },
}
```

## Step state in thread state

```rust
pub(crate) struct ActiveSkillStep {
    pub turn_id: String,
    pub snapshot: Arc<SkillRoutingSnapshot>,
    pub visible: Arc<HashSet<SkillIdentity>>,
    pub evidence: Arc<RoutingEvidence>,
    pub explicitly_selected: Arc<[SkillIdentity]>,
    pub recovery: Arc<Mutex<SkillRecoveryBudget>>,
}

pub(crate) struct SkillsThreadState {
    // existing fields...
    active_steps: Mutex<HashMap<String, Arc<ActiveSkillStep>>>,
}
```

Methods:

```rust
pub(crate) fn replace_active_step(
    &self,
    turn_id: String,
    state: Arc<ActiveSkillStep>,
);

pub(crate) fn active_step(
    &self,
    turn_id: &str,
) -> Option<Arc<ActiveSkillStep>>;

pub(crate) fn remove_active_step(&self, turn_id: &str);
```

No method may return “latest step” without an exact turn ID.

## Tool registration

The `skills` namespace becomes available whenever the skills extension is enabled and adaptive mode
or deferred reads require it. It must not depend solely on an orchestrator provider.

Register:

- `skills.search`;
- `skills.read`;
- retain `skills.list` only for its existing orchestrator/full-inventory use case, not as adaptive
  recovery.

`skills.search` and uniform `skills.read` use the active step state. Existing orchestrator behavior
must remain compatible.

## `skills.search` input schema

```rust
#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct SearchInput {
    /// Compact description of the capability or workflow needed.
    goal: String,

    /// Exact identities to exclude from this result.
    #[serde(default)]
    exclude: Vec<SkillIdentityInput>,

    /// Requested result count; defaults to 8 and is clamped to 1..=16.
    limit: Option<u8>,
}
```

Validation:

- `goal`: non-empty, no control characters, ≤2,048 bytes;
- `exclude`: ≤32 entries, each bounded;
- reject unknown fields;
- require active turn ID;
- require remaining recovery budget.

## `skills.search` output schema

```rust
#[derive(Debug, Serialize, JsonSchema)]
struct SearchOutput {
    matches: Vec<SearchMatchOutput>,
    has_more: bool,
    remaining_calls: u8,
    warnings: Vec<String>,
}

#[derive(Debug, Serialize, JsonSchema)]
struct SearchMatchOutput {
    authority: SkillAuthorityOutput,
    package: String,
    name: String,
    description: String,
    main_resource: String,
    access: SkillAccessKind,
}
```

The output must fit the cumulative 8,000-byte recovery budget. If normal serialization exceeds the
remaining budget, allocate fewer results; do not cut JSON in the middle.

## Uniform `skills.read` input

```rust
#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct ReadInput {
    authority: SkillAuthorityInput,
    package: String,
    resource: String,
    generation: u64,
    cursor: Option<String>,
    max_bytes: Option<u16>,
}
```

`max_bytes` defaults to 8,000 and is clamped to 1..=8,000.

`generation` is a process-local step-generation value returned in an explicit deferred reference or
search match. If exposing a raw integer to the model is undesirable, use an opaque signed/encoded
handle that contains the generation and identity.

## Uniform `skills.read` output

```rust
#[derive(Debug, Serialize, JsonSchema)]
struct ReadOutput {
    name: String,
    contents: String,
    complete: bool,
    next_cursor: Option<String>,
    bytes_returned: usize,
}
```

Properties:

- UTF-8 boundary safe;
- stable cursor bound to generation, identity, resource, and next offset;
- repeated same cursor returns the same page while snapshot lives;
- `complete=true` only at end;
- no overlap required;
- no content past 1 MiB;
- output marked external/untrusted context consistently with current tool outputs.

## Cursor

Cursor payload conceptually contains:

```text
generation | authority-hash | package-hash | resource-hash | byte-offset
```

It must be opaque to the model and integrity checked. Process-local random secret/HMAC is acceptable;
an in-memory nonce map is also acceptable if bounded and cleared with step state.

Never accept a raw byte offset without identity binding.

## Provider search naming

Current `SkillProvider::search(SkillSearchRequest)` is package-oriented and unused. Do not overload
it for catalogue discovery.

Choose one:

- rename it to `search_resources` in a compatibility-preserving refactor; or
- leave it unchanged and document it as package-resource search.

Add catalogue search at `SkillRoutingSnapshot`/selector level, not provider level.

## Rendering API unification

Generalize the mature core renderer to accept authority-neutral lines:

```rust
pub(crate) struct SkillRenderLine<'a> {
    pub name: &'a str,
    pub description: Cow<'a, str>,
    pub access_label: &'a str,
    pub locator: Cow<'a, str>,
}
```

Expose one function used by both full and candidate catalogue paths:

```rust
pub fn render_skill_catalogue(
    lines: Vec<SkillRenderLine<'_>>,
    budget: SkillMetadataBudget,
    side_effects: SkillRenderSideEffects<'_>,
) -> Option<AvailableSkills>;
```

Requirements:

- fair shortening;
- exact UTF-8 byte bound where required;
- aliases only for host paths and only when beneficial;
- deterministic ordering supplied by caller;
- report total/included/omitted/truncated;
- no source-specific read behavior in renderer.

Delete or redirect the extension's parallel simple renderer after parity tests pass.

## Instruction fragments

Create two context fragment structs:

```rust
struct InlineSkillInstructions { ... }
struct DeferredSkillInstructions { ... }
```

Both implement `ContextualUserFragment`.

`DeferredSkillInstructions` includes the exact tool handle and the requirement to read to
`complete=true`.

No context item may exceed repository limits.

## Routing diagnostics

Developer-only diagnostics may expose:

```rust
pub(crate) struct SkillRoutingReport {
    pub mode: SkillCatalogueModeKind,
    pub snapshot_entries: usize,
    pub implicit_entries: usize,
    pub full_render: SkillRenderReport,
    pub candidate_count: usize,
    pub candidate_bytes: usize,
    pub method: &'static str,
    pub query_script: QueryScript,
    pub router_duration: Duration,
    pub fallback_reason: Option<SkillRoutingFailureKind>,
}
```

Do not expose raw query text or identities by default.

## Configuration

Reuse `Feature::SkillSearch` for shadow/active routing rather than adding another overlapping flag.

Add an internal/config enum only if needed for rollout:

```rust
enum SkillSearchMode {
    Off,
    Shadow,
    Active,
}
```

Default migration:

- current `true` maps to `Shadow` until maintainers switch;
- active cutover explicitly maps to `Active`;
- `Off` preserves legacy.

If this changes public config schema, run `just write-config-schema`.

## Error types

Use explicit enums, not string-only control flow:

```rust
enum SkillRoutingFailureKind {
    CatalogueTooLarge,
    InvalidSourceBinding,
    RouterInternal,
    CandidateRenderFailed,
    SnapshotUnavailable,
}

enum SkillReadFailureKind {
    TurnNotActive,
    StaleGeneration,
    IdentityNotFound,
    ResourceMismatch,
    SourceUnavailable,
    ReadFailed,
    TooLarge,
    InvalidCursor,
}
```

User/model messages are bounded projections of these errors.

## Module layout

```text
ext/skills/src/
  routing/
    mod.rs
    evidence.rs
    evidence_tests.rs
    selector.rs
    selector_tests.rs
    snapshot.rs
    snapshot_tests.rs
    allocator.rs
    allocator_tests.rs
    limits.rs
  tools/
    search.rs
    read.rs
    list.rs
    schema.rs
  extension.rs
  state.rs
  catalog.rs
```

Keep implementation modules below repository size guidance and tests in sibling files.

## No new Rust dependencies unless justified

The current weighted selector uses standard collections. Prefer no new search/index dependency. If a
dependency is added:

- justify why existing code is insufficient;
- update Cargo files;
- run `just bazel-lock-update`;
- include `MODULE.bazel.lock`.
