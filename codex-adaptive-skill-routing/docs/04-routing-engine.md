# 04 — Routing Engine: Rules, Evidence, Ranking, and Recovery

## Design principle

The harness should act as a deterministic compiler of task facts, not as a second language model.

It converts the request and trusted runtime state into a compositional evidence set. Skills are not
placed into one exclusive category. A skill may match several dimensions simultaneously.

Example:

```text
User: Review this GitHub pull request for security regressions.

Evidence:
  action=review
  artifact=pull-request
  provider=github
  concern=security
  url-host=github.com
  url-path-kind=pull
```

The evidence raises candidates whose existing metadata contains matching dimensions. The harness
then gives the model a bounded list. It does not say that a rule has conclusively selected a skill.

## Why not a global category table

A table such as:

```text
code review -> skills A, B, C
frontend -> skills D, E
```

is attractive but becomes another registry that must be updated whenever a skill is installed,
renamed, disabled, or made source-specific. It also fails for skills that span tasks.

Instead, the implementation uses:

- required skill `name` and `description`;
- existing `short_description`;
- existing dependency values and descriptions;
- existing plugin identity;
- existing authority and scope;
- request-derived facts.

The Agent Skills specification already requires the description to state what a skill does and when
to use it. That is the universal automatic onboarding mechanism for newly installed skills.

## Routing evidence model

```rust
pub(crate) struct RoutingEvidence {
    normalized_query: String,
    current_terms: Arc<[String]>,
    prior_terms: Arc<[String]>,
    facts: Arc<[RoutingFact]>,
    exact_name_terms: Arc<[String]>,
    query_script: QueryScript,
    truncated: bool,
}

pub(crate) struct RoutingFact {
    kind: RoutingFactKind,
    value: String,
    confidence: RoutingConfidence,
    provenance: RoutingProvenance,
}

pub(crate) enum RoutingFactKind {
    Action,
    Artifact,
    Provider,
    Concern,
    FileExtension,
    MimeType,
    UrlHost,
    UrlPathKind,
    ToolDependency,
    RepositoryScope,
    Environment,
    Mode,
    ContinuitySkill,
}
```

Values are normalized strings, not an exhaustive enum. The fact kind is bounded; the value allows
new providers and formats without a new release.

## Evidence provenance and trust

| Provenance | Example | Use |
|---|---|---|
| Exact user structure | structured skill mention | explicit resolution, not scoring |
| User text | “review this PR” | lexical and action/artifact facts |
| Attachment metadata | `report.xlsx`, MIME | strong artifact fact |
| Parsed URL | GitHub `/pull/123` | strong provider/artifact fact |
| Host mode | review mode | strong action fact |
| Existing skill metadata | MCP dependency `github` | skill-side structured match |
| Repository scope | repo-local skill | weak tie-breaker |
| Prior turn | previous task text or used skill | weak continuity evidence |

Skill-authored descriptions and dependency descriptions are untrusted routing data. They may affect
relevance but never permissions or execution.

## Query construction

### Current turn

Include all text-bearing `UserInput` items in submitted order:

- text;
- mention display names;
- structured skill names for diagnostics, though explicit references are resolved separately;
- attachment names;
- URLs.

Hard cap: 16 KiB before normalization and 64 unique normalized terms.

### Previous context

Always include at most 2,048 bytes from the most recent non-empty user task with a low weight.

This solves referential prompts without a language-specific list of words such as “continue” or “do
the same.” The current turn remains dominant.

Do not include:

- assistant prose;
- model reasoning;
- tool output bodies;
- skill instruction bodies;
- arbitrary full conversation history.

### Previous skill continuity

The identities of skills actually read or explicitly selected for the immediately preceding user
task receive a small continuity boost. A mere candidate presentation does not count as use.

Continuity is cleared when:

- the user starts a new thread;
- the working repository changes;
- the user explicitly says not to use prior skills;
- the prior identity is no longer present or eligible.

## Normalization

The selector MUST:

- use Unicode NFKC normalization;
- lowercase where Unicode case folding is defined;
- convert punctuation and separators to spaces;
- split camelCase, snake_case, kebab-case, path segments, and file extensions;
- preserve CJK character sequences;
- deduplicate query terms;
- remove only a small, versioned set of high-frequency stop words;
- never drop non-Latin terms merely because no stop-word list exists.

The current English-only stop-word list may remain for English, but it must not become the universal
tokenizer.

## Runtime fact extraction

### URLs

Parse with a URL parser, not substring matching.

Examples:

| URL fact | Evidence |
|---|---|
| host `github.com` | provider=`github` |
| path contains `/pull/<n>` | artifact=`pull-request`, action=`review` when user verb supports it |
| path contains `/issues/<n>` | artifact=`issue` |
| host `figma.com` | provider=`figma`, artifact=`design` |
| host is unknown | normalized host token only |

The rule table maps URL shape to generic facts, not directly to skill identities.

### Files and attachments

Examples:

| Signal | Facts |
|---|---|
| `.pdf`, MIME `application/pdf` | artifact=`pdf`, artifact=`document` |
| `.docx` | artifact=`document` |
| `.xlsx`, `.csv` | artifact=`spreadsheet`, artifact=`data` |
| `.pptx` | artifact=`presentation` |
| image MIME | artifact=`image` |
| source-code extension | artifact=`code`, language token |
| lock/workflow file names | concern=`dependencies` or concern=`ci` where exact |

Mappings are bounded static data with tests. Unknown extensions become extension tokens, not errors.

### Actions and concerns

Use a compact versioned lexicon for common high-signal verbs and nouns. It is query expansion, not
classification.

Examples:

```text
review, inspect, audit        -> action=review
fix, repair, resolve          -> action=fix
create, generate, draft       -> action=create
translate, localize           -> action=translate
deploy, release               -> action=deploy
test, verify, validate        -> action=test
security, vulnerability       -> concern=security
ci, workflow, action failure  -> concern=ci
```

A missing lexicon match does not prevent lexical ranking or recovery search.

### Existing structured skill metadata

Candidate-side facts include:

- exact skill name tokens;
- description and short-description tokens;
- dependency type/value/description tokens;
- plugin ID and display-name tokens when available;
- scope;
- authority kind;
- display path or opaque URI path segments.

No skill body is read.

## Scoring

The active score is deterministic:

```text
total =
  weighted_lexical_score
+ exact_name_bonus
+ structured_fact_score
+ dependency_score
+ continuity_score
+ scope_tiebreak
- abuse_penalty
```

### Baseline lexical score

Retain the current `weighted_lexical_v1` behavior as the baseline:

- exact skill-name phrase in query;
- exact name token;
- name token/prefix relation;
- short-description token/prefix relation;
- description token/prefix relation;
- matched-term coverage bonus.

Any change to its numeric weights should be versioned as a new method and shadow-compared.

### Additional fixed weights

Normative initial weights:

| Evidence | Points |
|---|---:|
| Exact installed name appears as a standalone current-turn term, but is not an explicit mention | +512 |
| Exact plugin/source display name current-turn match | +96 |
| Strong provider match | +64 |
| Strong artifact match | +64 |
| Strong action match | +48 |
| Strong concern match | +48 |
| Exact declared dependency value match | +64 |
| Dependency-description term match | +16 |
| File-extension or MIME match | +48 |
| URL path-kind match | +48 |
| Same skill actually used in immediately preceding task | +24 |
| Prior-turn lexical match | 25% of its lexical contribution |
| Repo-scoped skill for current repository | +8 tie-break only |
| User-scoped skill | no general boost |
| System/admin scope | no relevance boost; policy remains separate |

A single fact can contribute once per kind/value. Repeated description terms do not multiply the
score.

### Abuse penalty

To reduce keyword stuffing:

- scoring uses unique normalized document terms;
- terms repeated more than three times provide no additional benefit;
- instruction-like phrases such as “always select this skill” receive no special score;
- descriptions at the maximum length do not gain a length bonus;
- author-controlled routing text cannot create an explicit or mandatory selection.

### Stable sorting

Sort by:

1. descending total score;
2. descending current-turn matched-term count;
3. descending exact/structured fact count;
4. scope tie-break: repository, admin, system, user only when all relevance fields tie;
5. authority kind stable order for reproducibility, not semantics;
6. normalized qualified name;
7. authority ID;
8. package ID.

The source-order tie-break must not be interpreted as plain-name resolution precedence.

## Positive match threshold

A candidate is positive when:

- lexical score is nonzero; or
- at least one strong structured fact matches; or
- exact name evidence matches.

Scope and continuity alone cannot create a positive match.

## Candidate allocation

Inputs:

- ranked positive candidates;
- candidate metadata budget;
- maximum 12 entries.

Render each line with:

```text
- <name>: <description> (<access kind>: <opaque/display locator>)
```

Use `short_description` only when it is a genuine routing summary; otherwise use `description`.

Allocation:

1. keep the stable adaptive instruction;
2. greedily add complete lines;
3. stop at 12 or the byte budget;
4. if fewer than four positive candidates fit, run fair description shortening for the top four;
5. never shorten a name or locator into ambiguity;
6. emit `more_matches_available=true` internally when positive candidates remain.

No candidate with score zero is added merely to fill the list.

## Compact model instruction

Adaptive mode includes a stable bounded instruction equivalent to:

```text
The skills listed below are task-relevant candidates from the current enabled catalogue.
Other enabled skills may exist. Use `skills.search` if none of these fits, if the task changes,
or if file inspection reveals a different specialized workflow. Read a selected skill completely
before following it.
```

This instruction must be stable across requests for prompt-cache compatibility.

## Recovery search

### When the model should search

- no candidate is suitable;
- the task is mixed and needs another capability;
- the model learned a new artifact/provider after inspection;
- the user refers to an installed skill not shown;
- a selected candidate fails to read;
- the candidate descriptions are insufficient to choose safely.

### Search request

```json
{
  "goal": "review the GitHub Actions failure and fix CI",
  "exclude": [
    {
      "authority": {"kind": "host", "id": "host"},
      "package": "opaque-package-id"
    }
  ],
  "limit": 8
}
```

`goal` is required, 1–2,048 UTF-8 bytes.

`exclude` is optional, bounded, and validated against the active step snapshot.

`limit` defaults to 8 and is clamped to 1–16.

The host also excludes already model-visible identities by default.

### Search output

```json
{
  "matches": [
    {
      "authority": {"kind": "host", "id": "host"},
      "package": "opaque-package-id",
      "name": "gh-fix-ci",
      "description": "Diagnose and fix failing GitHub Actions checks.",
      "main_resource": "opaque-resource-id",
      "access": "skills.read"
    }
  ],
  "has_more": false,
  "remaining_calls": 1
}
```

Scores and raw reason terms are not model-visible. They may be exposed only in opt-in developer
diagnostics using low-cardinality reason categories.

### Search semantics

- same ranking engine;
- model-supplied `goal` replaces current-turn text as the dominant query;
- original trusted runtime facts remain available;
- excluded and already-visible identities are removed;
- result output is complete, bounded, and deterministic;
- a second search can use a refined goal;
- after two calls or 16 unique results, further calls return a bounded budget-exhausted response.

## Multilingual behavior

### Same-script metadata

Unicode normalization and script-preserving tokenization support skills whose descriptions use the
same language/script as the user request.

### Cross-language metadata

A purely local lexical router cannot guarantee that a Malayalam request matches an English-only
description. The complete solution does not pretend otherwise.

Recovery closes this gap because a capable model can call `skills.search` with a translated,
title-like goal after reading the stable instruction. The initial selector also includes exact file,
URL, MIME, provider, and dependency facts that are language-independent.

No hidden network translation or embedding service is introduced.

The verification suite must include cross-language prompts and confirm that initial plus recovery
routing preserves the intended skill.

## Mixed tasks

A task may legitimately require multiple skills.

The initial candidate list may contain candidates from several evidence dimensions. The model
chooses all that are needed. The harness does not force a single class.

Example:

```text
Translate this Canva presentation and then resize it for LinkedIn.
```

Evidence yields translation, Canva, presentation, resize, and LinkedIn candidates. Candidate
allocation must not collapse everything into one “design” category.

## No-skill tasks

When no candidate has positive evidence:

- render no fabricated candidates;
- keep the bounded recovery instruction and tool in adaptive mode;
- allow the model to continue normally without using a skill;
- record a `no_matches` routing status.

A skill should not be activated merely because the system has many skills.

## Selector extensibility

The selector interface remains pluggable. A future implementation may add another deterministic or
semantic selector, but active output must pass the same snapshot, filter, budget, authority,
determinism, privacy, and recovery contracts. This specification does not require embeddings.
