# 11 — Verification and Test Plan

## Verification philosophy

This change affects agent logic and model-visible context. Repository guidance requires integration
tests for major agent changes. Unit tests alone are insufficient.

Verification has five layers:

1. deterministic unit/property tests;
2. extension/provider integration tests;
3. `codex-core` end-to-end request tests;
4. compatibility and load tests;
5. upstream shadow/active telemetry comparison.

All five are required.

## Ground truth

### Explicit

Ground truth is exact resolution against the captured explicit-available snapshot.

### Implicit

Ground truth sources:

- structured host skill-body read/injection event;
- structured executor skill-body read/injection event;
- structured orchestrator `skills.read`;
- custom provider read/injection;
- labeled offline benchmark.

Do not rely solely on shell-command heuristic observation. Add structured invocation events to every
authority-preserving read/injection path.

### Negative tasks

Ground truth is “no skill required” or an allowed set of optional skills. Evaluation must measure
false activation, not only recall.

## Shadow evaluation

The current default-enabled shadow selector already records whether later observed invocation appears
within its top 20. Extend it before active cutover.

### Required methods compared

- current `weighted_lexical_v1`;
- policy-assisted fused selector;
- full legacy visible catalogue behavior;
- adaptive initial plus recovery in controlled integration evals.

### Required metrics

| Metric | Dimensions |
|---|---|
| selector run count | method, mode, query-script |
| duration | method, catalogue-size bucket |
| catalogue entries | source-kind distribution |
| positive candidates | bucket |
| initial visible candidates | bucket |
| metadata reduction | basis-point bucket |
| observed invocation hit | rank bucket 1, 2–5, 6–10, 11–20, miss |
| source coverage | host, executor, orchestrator, custom |
| search calls | 0, 1, 2 |
| recovery hit | initial miss/recovery hit |
| no-match | boolean |
| fallback | reason enum |
| explicit failure | reason enum |
| read pages | count bucket |
| stale handle | boolean |
| candidate bytes | bucket |
| full-render loss | none, shortened, omitted, both |

No raw labels or identities.

## Cutover gates

Fleet-wide values are maintainers' evidence; this package does not fabricate them.

Active mode may replace lossy catalogue rendering only when all of these are true:

1. explicit parity is 100% in deterministic tests;
2. disabled/implicit-hidden leakage is zero;
3. authority mismatch/stale read is zero;
4. offline benchmark intended-skill recall for initial plus recovery is at least 99%;
5. fused selector recall is no worse than lexical baseline at the same output budget;
6. negative-task false activation does not regress materially;
7. warm local selector p95 is below 20 ms for 1,000 entries and below 100 ms for 10,000 entries on the
   maintainer reference machine;
8. candidate metadata is at least 75% smaller at median than the lossy full catalogue it replaces;
9. search output and body pages remain within hard caps;
10. no duplicate catalogue injection appears in request snapshots;
11. resume, fork, compaction, environment availability, and plugin refresh integration tests pass;
12. maintainers approve any changed app-server/tool/context contract.

If fleet data is insufficient, keep shadow collection active until statistically meaningful. This is
verification work, not an optional product phase.

## Unit tests

### Evidence

- Unicode NFKC;
- camel/snake/kebab splitting;
- URL parsing;
- GitHub pull/issue path facts;
- known and unknown file extensions;
- MIME facts;
- action/concern lexicon;
- malformed URL;
- control characters;
- current/prior weighting;
- prior context byte cap;
- no assistant/tool-body inclusion.

### Selector

Retain all current weighted lexical tests and add:

- exact-name bonus;
- provider/artifact/action/dependency scoring;
- no scope-only positive match;
- keyword repetition cap;
- deterministic ties;
- same input same output;
- all authority kinds;
- 10,000 entries;
- cap overflow;
- non-Latin scripts;
- prior-turn low weight;
- current turn dominance;
- exact structured mentions excluded from ordinary candidate ranking when closed set.

### Allocator

- complete descriptions fit;
- max 12;
- exact UTF-8 byte cap;
- minimum four fallback;
- name/locator never omitted;
- one giant description;
- no positive candidates;
- has-more;
- alias versus opaque locator;
- multibyte boundaries.

### Snapshot

- filters;
- explicit versus implicit views;
- duplicate identity;
- duplicate name;
- source-generation mismatch;
- read-route mismatch;
- host routing metadata projection;
- plugin identity;
- product gating;
- immutable clone behavior.

### Cursor/read

- page concatenation exactly equals original;
- newline optimization does not skip/duplicate;
- final complete flag;
- invalid cursor;
- altered cursor;
- wrong turn;
- wrong generation;
- wrong identity;
- 1 MiB boundary;
- over 1 MiB;
- multibyte boundary;
- concurrent same-page reads.

## Property and fuzz tests

Recommended targets:

- query normalizer never panics for arbitrary Unicode;
- rendering never exceeds byte cap;
- pagination reassembles input for arbitrary valid UTF-8;
- cursor decoder rejects arbitrary bytes safely;
- sorted results are deterministic under randomized input order;
- disabled entries never appear in candidate/search output;
- every returned identity exists in the supplied snapshot;
- read route authority always equals identity authority;
- JSON output is valid under every remaining-byte boundary.

## Extension integration tests

Use fake providers for host, executor, orchestrator, and custom sources.

Scenarios:

1. full lossless catalogue;
2. adaptive on shortening;
3. adaptive on omission;
4. explicit closed set;
5. explicit open set;
6. recovery search then read;
7. initial miss then recovery hit;
8. no match;
9. stale generation;
10. source disconnect;
11. duplicate plain name;
12. oversized instruction pagination;
13. provider wrong-resource response;
14. recovery budget exhaustion;
15. thread cleanup;
16. config change;
17. orchestrator generation replacement;
18. executor ready/unready projection;
19. custom authority.

## Core end-to-end tests

Repository guidance prefers integration tests under `core/tests/suite`.

Mock response sequences should assert the exact request shape.

### Lossless path

- complete catalogue appears once;
- search guidance not unnecessarily injected;
- model reads selected skill;
- invocation event emitted.

### Adaptive path

- full catalogue absent;
- candidate catalogue appears once;
- candidate bytes bounded;
- `skills.search` tool visible;
- model searches;
- second request contains bounded search output;
- model reads;
- exact body pages supplied;
- no duplicate metadata.

### Explicit multi-skill

- user submits three structured skills;
- all exact bodies/references present in order;
- no adaptive extras for closed set;
- one missing causes no model request;
- open set includes pinned plus candidates.

### Lifecycle

- first step executor unavailable;
- next step executor ready and candidates replaced;
- disconnect removes next step;
- old handle rejected;
- resume reconstructs;
- compaction recomputes;
- fork has independent budget/state.

## Compatibility tests

- existing app-server `skills/list`;
- picker/toggle;
- `skills.config` enable/disable;
- bundled toggle;
- `allow_implicit_invocation=false`;
- product restriction;
- existing orchestrator `skills.list`/`skills.read` request compatibility where retained;
- old feature boolean migration;
- rollout resume;
- Windows path normalization;
- remote executor;
- CLI and desktop/app-server prompt snapshots.

## Model behavior eval corpus

Create a checked-in, license-safe synthetic benchmark. It contains metadata and prompts, not user
telemetry.

Each case:

```json
{
  "id": "github-ci-001",
  "prompt": "Fix the failing GitHub Actions checks on this PR.",
  "runtime_facts": {
    "urls": ["https://github.com/acme/repo/pull/42"]
  },
  "skills": [
    {
      "identity": "host/gh-fix-ci",
      "name": "gh-fix-ci",
      "description": "Diagnose and fix failing GitHub Actions checks."
    },
    {
      "identity": "host/decoy",
      "name": "github-summary",
      "description": "Summarize GitHub repository activity."
    }
  ],
  "expected": {
    "required": ["host/gh-fix-ci"],
    "allowed": [],
    "forbidden": ["host/decoy"]
  }
}
```

Required categories:

- code review;
- CI;
- issue triage;
- frontend/design;
- PDF/document;
- spreadsheet;
- slides;
- translation;
- image;
- deployment;
- security;
- mixed tasks;
- no-skill;
- ambiguous;
- typo;
- same-name authorities;
- heavily shortened trigger boundary;
- omitted intended skill;
- malicious decoy;
- referential follow-up;
- multilingual same-script;
- cross-language recovery;
- newly installed skill;
- unavailable executor.

At least 200 cases before active cutover, with balanced negative cases. Numbers can grow; 200 is the
minimum required verification corpus, not an MVP feature boundary.

## Performance benchmarks

Benchmarks at:

- 10;
- 100;
- 1,000;
- 5,000;
- 10,000

entries, using short and maximum-length descriptions.

Measure:

- snapshot document projection;
- normalization;
- ranking;
- allocation;
- memory;
- repeated search on same snapshot;
- multibyte descriptions.

No network or file I/O in selector benchmark.

## Repository checks

From `codex-rs`:

1. `just fmt`
2. `just test -p codex-skills-extension`
3. `just test -p codex-core-skills`
4. affected app-server/core integration tests through `just test -p ...`
5. `just fix -p codex-skills-extension`
6. `just fix -p codex-core-skills` if changed
7. `just write-config-schema` if config types changed
8. `just bazel-lock-update` if Rust dependencies changed
9. `just argument-comment-lint`
10. full `just test` before final upstream submission according to maintainer workflow
11. `git diff --check`
12. snapshot review for any user-visible text/UI change.

Do not run `cargo test` directly.

## Acceptance report

The final PR stack must include a machine-readable or Markdown acceptance report listing:

- baseline/head;
- changed modules;
- tests run;
- benchmark results;
- shadow metric query/version;
- cutover gate results;
- known environment-skipped tests;
- config/schema changes;
- lockfile changes;
- model-visible prompt snapshots;
- rollback procedure.

No gate may be marked passed without evidence.
