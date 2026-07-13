# 06 — Authority, Snapshot, and Lifecycle Semantics

## Authority is part of identity

A skill identity is:

```rust
pub(crate) struct SkillIdentity {
    pub authority: SkillAuthority,
    pub package: SkillPackageId,
}
```

The main prompt is a resource inside that identity. Two entries with the same display name are still
different skills when authority or package differs.

No component may derive a host path from an executor/orchestrator URI or route a host path through a
remote provider.

## Authority behavior

### Host

Source:

- bundled/system skills;
- admin skills;
- user skills;
- repository skills;
- plugin-installed or materialized host skills.

Snapshot owner: `SkillsService` / `HostSkillsSnapshot`.

Read owner: filesystem captured by `HostSkillsSnapshot`.

Freshness:

- configuration-specific cache keys;
- explicit cache clear;
- local file watcher;
- plugin lifecycle invalidation.

### Executor

Source: a ready selected capability root in an execution environment.

Snapshot owner: executor catalogue/cache associated with selected root and environment identity.

Read owner: exact environment/resource route captured for the current step.

Freshness:

- selected root is treated as stable for the thread under the current product assumption;
- availability may change per model step;
- disconnect removes projection for the next step;
- reconnect to the same logical environment may reuse metadata;
- a genuinely replaced logical source must receive a new generation/identity.

### Orchestrator

Source: hosted MCP `mcp/skill` resources.

Snapshot owner: orchestrator catalogue cache keyed by MCP resource client generation.

Read owner: the same orchestrator authority and MCP generation.

Freshness:

- re-list when the MCP generation changes;
- preserve current immutable snapshot for in-flight calls;
- enforce existing pagination, timeout, malformed-resource, and resource-size limits.

### Custom

A custom provider must publish:

- stable authority kind and ID;
- package identity;
- metadata;
- main resource;
- read route;
- generation semantics.

If it cannot supply immutable step-safe identity, it cannot participate in adaptive search.

## Snapshot construction

### Input

```rust
pub(crate) struct SkillRoutingSnapshotInput {
    pub turn_id: String,
    pub host: Option<Arc<HostSkillsSnapshot>>,
    pub host_catalog: SkillCatalog,
    pub executor_catalogs: Vec<BoundSkillCatalog>,
    pub orchestrator_catalog: Option<BoundSkillCatalog>,
    pub custom_catalogs: Vec<BoundSkillCatalog>,
}
```

`BoundSkillCatalog` carries both entries and the source object/generation that can read them.

### Validation

For every entry:

1. authority is supported;
2. package ID is non-empty and bounded;
3. main resource is non-empty and bounded;
4. name and routing descriptions satisfy existing loader/provider limits;
5. read route authority equals entry authority;
6. source generation is present;
7. enabled and prompt visibility fields are explicit;
8. duplicate identity is handled deterministically.

### Duplicate identity

If two sources publish the exact same authority plus package:

- keep the first source in configured deterministic source order;
- emit a bounded duplicate-identity warning;
- never merge descriptions or read routes.

Same name with different identity is not a duplicate.

## Generation

A generation is process-local and opaque:

```rust
#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq)]
pub(crate) struct SkillRoutingGeneration(u64);
```

It increments whenever the effective bound snapshot changes.

The generation is not persisted across process restart and is not a security token. It prevents a
model/tool call from accidentally using a handle against a different snapshot.

## Step immutability

Once published for a model request:

- entry vectors do not change;
- enabled state does not change;
- read bindings do not change;
- candidate visibility does not change;
- recovery budget counters may decrease;
- provider caches may memoize content without changing semantics.

## Host file change

### During current step

The watcher may clear the service cache, but the captured `Arc<HostSkillsSnapshot>` remains valid for
the current step. If the underlying local file itself was deleted before read, the read can fail.
The system must not silently load a newly created same-name skill.

### Next step

Reconstruct from the refreshed service snapshot. The new or edited skill automatically becomes a new
routing document.

## Skill installation

### Host/plugin install

- existing plugin/skills owner installs and validates;
- existing cache invalidation runs;
- current step is unchanged;
- next step sees the new generation;
- new skill participates automatically using name/description and existing metadata.

### Remote/executor install

The current product treats selected root contents as stable for the thread. Therefore a remote
in-place install is not assumed visible unless the environment/root owner publishes a new stable
generation or the thread selects a new root.

The router must not add a filesystem watcher to a remote executor.

## Disable or uninstall

### Before snapshot

Entry is absent from the relevant explicit/implicit view according to existing policy.

### After snapshot, before tool call

The exact current-step snapshot remains the reference. For host files, an uninstall can make the
read fail. For hosted providers, generation-bound source access decides whether the old resource
remains readable.

A failure is reported as stale/unavailable. The tool must not search the next generation for a
same-name replacement.

### Next step

The disabled/uninstalled entry is absent.

## Plugin upgrade

A plugin upgrade can leave old cache directories on disk. The router never scans those directories.
Only active plugin roots supplied by the plugin owner enter `SkillsService`.

A plugin version replacement must:

- invalidate the effective host/plugin generation;
- retain old snapshot validity for in-flight work where possible;
- give changed package identities or source generations a new routing generation;
- prevent a search result from the old version being read through the new version.

## Environment availability

### Executor pending on first step

The executor skill is not in the effective snapshot until its selected root is ready.

If the user explicitly selected a structured executor skill before readiness, the existing capability
selection/dependency path may wait according to current policy. If readiness fails, explicit
selection fails.

### Executor becomes ready later

The next model step builds a new snapshot that includes it. Candidate world state is replaced.

### Executor disconnects

The next step removes its entries. Current in-flight reads either complete through their captured
handle or fail.

### Same logical executor reconnects

Metadata may be reused only when the environment manager states the logical identity and selected
root contents are stable. The current connection handle is not part of stable identity; the read
route binds to the ready connection for the step.

### Different executor replaces same ID

This violates the current stability assumption. The environment owner must issue a new logical
generation. UASR treats it as a different source.

## Orchestrator refresh

The orchestrator catalogue is cached per MCP resource-client generation.

- same generation: reuse catalogue and resource cache;
- new generation: re-list on next step;
- timeout on first page: source unavailable;
- timeout after completed pages: bounded partial catalogue plus warning is allowed only if existing
  provider semantics already allow it; adaptive search must disclose `catalog_incomplete` internally;
- malformed resources are excluded;
- more than provider page/skill caps produces bounded warning.

An incomplete provider catalogue cannot be made complete by host-side ranking.

## Resume

On resume:

1. reload effective host/plugin configuration;
2. reconstruct current selected environment state;
3. reconstruct orchestrator generation;
4. build a new routing snapshot;
5. do not reactivate old candidate lists from history;
6. preserve structured explicit references in replayed user input according to existing protocol;
7. reject old process-local search handles.

## Fork

A fork inherits conversation history but builds its own current effective routing snapshot. Candidate
state, recovery budget, and process-local generation are not copied as active state.

## Compaction

Candidate catalogues are contextual state, not durable instructions.

Compaction must preserve:

- user task;
- explicit skill selections that remain relevant to the ongoing task;
- material results produced under a skill;
- ordinary conversation semantics.

Compaction must not preserve:

- an old candidate list as if still current;
- exhausted recovery counters;
- stale opaque handles;
- old source generations;
- skill descriptions merely because they were once candidates.

After compaction, the next model step recomputes candidates.

## Thread/turn cleanup

On turn stop, abort, or terminal error:

- remove active step state from `SkillsThreadState`;
- release snapshot references not held by in-flight work;
- clear recovery counters;
- retain only low-cardinality completed metrics;
- do not retain raw routing query text.

On thread stop:

- drop executor/orchestrator routing caches owned by the thread;
- allow shared owner caches to follow their existing lifecycle.

## Configuration changes

A committed effective config change:

- updates `SkillsExtensionConfig`;
- invalidates or replaces affected host snapshot through existing service logic;
- takes effect on the next step;
- does not mutate an in-flight step.

Changing only UI visibility must not accidentally change model routing unless that setting is the
existing enablement or prompt-visibility policy.

## Product gating

Product restrictions must be enforced before snapshot construction. The router must not rank a skill
and rely on read-time rejection.

The current `SkillPolicy.products` TODO indicates this boundary requires careful verification. The
completed implementation must confirm that every source applies product gating consistently.

## State transition table

| Event | Current step | Next step |
|---|---|---|
| Local skill edited | unchanged; old read may fail if file replaced | refreshed metadata |
| New local skill installed | absent | present |
| Skill disabled | unchanged snapshot | absent |
| Plugin upgraded | old generation | new active generation |
| Executor becomes ready | absent unless step rebuilt before request | present |
| Executor disconnects | in-flight read completes/fails | absent |
| MCP generation changes | old bound generation | relisted |
| Thread resumes | n/a | new snapshot |
| Conversation compacts | old step ends | candidates recomputed |
| Search handle from old generation | reject | reject |
