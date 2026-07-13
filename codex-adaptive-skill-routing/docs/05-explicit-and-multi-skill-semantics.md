# 05 — Explicit and Multi-Skill Invocation Semantics

## Purpose

Explicit selection is the user's deterministic routing instruction. It must not be weakened by
adaptive discovery.

## What counts as explicit

The harness treats these as exact explicit references:

1. a structured `UserInput::Skill` created by the picker or client;
2. a valid `$skill-name` mention;
3. an exact source-qualified mention supported by the client;
4. an exact opaque skill locator supplied through a structured input.

Plain prose such as “use the code review skill” without a structured or `$` reference remains a
strong implicit hint unless the client has already encoded it as a structured skill input. This
avoids unreliable language-specific parsing.

Clients SHOULD convert picker selections into structured inputs. Documentation and diagnostics
SHOULD recommend `$name` for deterministic text-only use.

## Resolution algorithm

```text
for each explicit reference in user order:
    resolve exact identity/path/qualified name
    reject disabled
    retain implicit-disabled skills
    detect ambiguity
    deduplicate by authority + package
if any required reference failed:
    stop before model execution
else:
    load or reference every resolved skill
```

### Exact structured identity

An authority/package/resource reference is resolved only within that authority. It must not be
reinterpreted as a local path or plain name.

### Exact host path

A structured host path must equal a skill path in the captured host snapshot after existing path
normalization. No ambient filesystem search is permitted.

### Plain `$name`

A plain name succeeds only if exactly one enabled explicit-available entry has that name after the
existing mention/connector conflict rules.

### Qualified name

A client/source-qualified name succeeds when it resolves to one identity. The qualifier is not
discarded after resolution.

## Multiple skills

When the user selects X, Y, and Z:

- all three are required;
- user order is preserved as the default coordination order;
- duplicate references to the same identity are collapsed at the first occurrence;
- the full catalogue is not needed to discover them;
- adaptive implicit selection is suppressed unless supplementation was permitted;
- each skill remains separately identifiable in model context and telemetry.

Example model-visible coordination instruction:

```text
The user explicitly selected these skills in this order:
1. X
2. Y
3. Z

Use every selected skill. Treat the order as a sequencing preference, not as permission to violate
higher-priority instructions. Read every selected skill completely before relying on it. If two
selected skills impose irreconcilable requirements, report the conflict instead of silently ignoring
one.
```

## Partial failure policy

Explicit selection is fail-closed by default.

| Condition | Required behavior |
|---|---|
| All references resolve | Continue with all |
| One reference missing | Do not substitute; return missing reference and bounded close matches |
| One reference disabled | State installed-but-disabled; do not load any required set unless best effort was explicit |
| One source unavailable | Report source unavailability and identity |
| Plain name ambiguous | Return source-qualified choices |
| Stale structured handle | Report stale handle; show current exact matches if available |
| Read error | Stop before acting under the incomplete set |
| Dependency startup failure | Report the selected skill and dependency; no silent omission |
| User explicitly requested best effort | Load all valid references and clearly identify skipped ones |

Failing the whole required set is intentional: executing with X and Y when the user required X, Y,
and Z can produce a materially different workflow.

## Implicit supplementation

### Closed set

These formulations indicate a closed set when encoded with exact references:

```text
Use $x, $y, and $z for this task.
Use only $x and $y.
```

The harness:

- injects/defers X, Y, Z;
- does not expose an adaptive candidate list for additional ordinary skills;
- keeps mandatory platform and dependency behavior;
- keeps `skills.search` hidden unless one selected skill instructs the model to find another skill or
  the user later changes the instruction.

### Open set

These formulations permit supplementation:

```text
Use $x and any other relevant skills.
Start with $x, then use whatever else is necessary.
```

The exact references are pinned and the adaptive candidate list is computed for the remainder.

The parser does not infer open/closed semantics from arbitrary prose. Clients may encode an
`allow_implicit_supplement` flag in structured input; otherwise exact references default to closed.

## Dependencies are not automatically “extra skills”

A skill's declared MCP/tool dependency is setup metadata, not another skill selection. Dependency
readiness follows the existing explicit dependency path.

If a skill body explicitly requires another named skill, the model may invoke it. The harness should
not parse arbitrary skill prose to infer a dependency graph during routing.

## Conflicting skill instructions

The harness cannot reliably perform semantic conflict analysis without reading and interpreting all
skill bodies. The model receives a stable coordination rule.

Conflict precedence:

1. system/platform safety and policy;
2. product/admin/configuration constraints;
3. user task and explicit selection;
4. compatible instructions from all selected skills;
5. user-selected ordering preference;
6. model judgment for non-conflicting implementation choices.

Examples:

### Edit versus review-only

- X says “modify the code.”
- Y says “review only; do not change files.”

If the user asked to edit and explicitly selected both, the model must state the conflict and not
silently pick one. If the conflict can be resolved by sequencing—review first, then edit—it may do so
only when both instructions allow it.

### Different output formats

If one skill requires JSON and another requires Markdown, the model should determine whether both can
be delivered separately. If not, report the conflict.

### Different tools for the same action

A preference conflict that does not change required output may be resolved using user order or the
more specifically applicable skill. The resolution must not violate an explicit prohibition.

## Ordering

User order is preserved in:

- injected instruction fragments;
- deferred reference list;
- diagnostics;
- invocation telemetry.

Order is a sequencing preference. It is not a security priority and does not make later instructions
override earlier ones.

## Instruction loading and aggregate size

### Inline path

Complete bodies may be inlined when:

- each body is at most 8,000 UTF-8 bytes;
- no more than eight bodies are inlined;
- aggregate inline bodies are at most 32,000 bytes.

### Deferred path

Any selected body that exceeds an inline limit becomes a required deferred reference. The harness
does not truncate it.

Example:

```text
Selected skill `$large-review` must be read before use.
Handle: {authority, package, resource, generation}
Use `skills.read` until `complete=true`.
```

If X and Y fit but Z does not, X and Y may be inline while Z is deferred. This is not partial
selection; all remain required.

### Read maximum

A main prompt above 1 MiB is rejected as invalid for model use with an actionable diagnostic. The
skill author should split detailed material into references. The Agent Skills standard recommends
splitting long `SKILL.md` content into referenced files.

## Skill becomes unavailable after explicit resolution

The current model step keeps its immutable source binding.

- If the source remains readable through the captured binding, the step may complete.
- If the source connection disappears before read, the read fails; do not silently resolve the same
  name from another source.
- A later model step may construct a new snapshot, but the user must re-resolve or receive a clear
  replacement diagnostic.
- A different source with the same name is not an automatic replacement.

## Duplicate names across scopes and authorities

The picker may show both. Exact structured selection distinguishes them.

A plain `$deploy` with two enabled matches is ambiguous even if one is repository-scoped and one is
user-scoped. Scope ordering is useful for catalogue rendering and ranking tie-breaks; it is not
permission to reinterpret an explicit name.

## `allow_implicit_invocation=false`

An enabled skill with this policy:

- does not enter implicit ranking;
- does not appear in adaptive search;
- remains visible to the picker where current policy allows;
- resolves through exact explicit invocation;
- may be inlined or deferred like any selected skill.

## Close matches

Close matches are diagnostic only.

For a missing explicit name, return at most five enabled explicit-available names using:

1. exact normalized prefix;
2. bounded edit/trigram similarity;
3. source/plugin label match.

The user or model must choose one. No close match is loaded automatically.

## Telemetry

For each explicit set, record only low-cardinality facts:

- number requested;
- number resolved;
- number inline;
- number deferred;
- failure category;
- authority-kind distribution;
- whether supplementation was permitted.

Do not emit skill names, paths, handles, or bodies.

## Required tests

- one structured explicit skill;
- multiple structured skills in order;
- repeated same identity;
- same name on two authorities;
- disabled selected skill;
- implicit-disabled selected skill;
- missing name with close matches;
- stale handle after refresh;
- source disconnect before read;
- dependency unavailable;
- closed set suppresses candidates;
- open set pins explicit plus candidates;
- aggregate inline overflow;
- one oversized body;
- more than eight selected skills;
- body over 1 MiB;
- conflict coordination instruction;
- resume/fork with structured selections;
- connector name collision;
- Unicode skill name constraints and path normalization.
