# 16 — Coding Assistant Execution Instructions

## Role

You are implementing Unified Adaptive Skill Routing in `openai/codex`.

Treat this document set as the functional source of truth, pinned to commit `8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66`. Treat the
current repository as the source of truth for file locations and already-landed refactors.

Do not implement only a demo, MVP, host-only patch, omission-only patch, or search-tool prototype.

## Before changing code

1. Read every document in this package in numeric order.
2. Read repository `AGENTS.md`.
3. Fetch current `main`.
4. Compare current `main` with `8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66` for every file named in `12-implementation-plan.md`.
5. Search current issues/PRs for `skill_search`, `dynamic_skill_selector`, `skills.search`,
   `SkillsSnapshot`, and `available_skills`.
6. Produce a baseline-drift note:
   - upstream changes;
   - requirements already satisfied;
   - renamed/deleted modules;
   - conflicts;
   - revised file map.
7. Do not restore obsolete parallel paths.

## Implementation discipline

- Work in reviewable dependent branches/commits.
- Every commit must compile and have coherent tests.
- Keep complex logic out of `codex-core` when an extension/core-skills owner exists.
- Preserve source authority.
- Never use an ambient path for a non-host resource.
- Never add a second filesystem scanner or persistent skill database.
- Never log raw prompts, skill metadata, handles, or bodies.
- Never silently truncate selected skill instructions.
- Never silently substitute an explicit skill.
- Never add a mandatory author taxonomy.
- Never switch active behavior before shadow/verification gates.
- Never treat a candidate rank as execution permission.

## Required order of work

1. Shared authority-neutral rendering.
2. Routing metadata projection and identity.
3. Immutable per-step routing snapshot.
4. All-authority structured invocation observation.
5. Evidence builder and fused selector in shadow.
6. Candidate allocator and full-versus-adaptive mode.
7. Catalogue `skills.search`.
8. Uniform paginated `skills.read`.
9. Explicit multi-skill/closed-open semantics.
10. Active adaptive cutover with degraded fallback.
11. Context replacement/compaction/resume/fork.
12. Diagnostics, benchmark, acceptance report.
13. Remove obsolete temporary/parallel code.
14. Run complete repository checks.

A different code order is acceptable only when dependency analysis proves it safer; functional
completion order remains the same.

## Required design checks before each PR

- Which requirement IDs are implemented?
- Which authority types are involved?
- Which model-visible items change?
- Are all new items bounded?
- Does the change alter cache prefixes?
- Does it affect persisted rollouts or app-server API?
- Does it affect config schema?
- Can explicit invocation regress?
- Can disabled/implicit-hidden skills leak?
- Can a stale handle be used?
- Can two catalogue owners inject simultaneously?
- What is the rollback behavior?
- Which integration test proves the user-visible behavior?

## Code review guardrails

Reject your own patch if it:

- searches only `HostSkillsSnapshot`;
- takes only the first 1,000 entries without a documented failure;
- activates only on omission;
- returns a fixed top five;
- relies on scope as permission;
- automatically prefers one authority for ambiguous explicit names;
- registers search only when orchestrator is available;
- overloads package-resource search as catalogue discovery;
- stores “latest” step state without exact turn ID;
- makes a tool handle valid across generations;
- truncates JSON or UTF-8 output to meet a byte limit;
- preserves old candidate lists through compaction;
- adds unbounded warnings;
- uses raw model text in telemetry;
- changes `weighted_lexical_v1` metric semantics without versioning;
- introduces a dependency without Bazel lock update;
- leaves required edge cases as TODOs.

## Testing workflow

Use repository commands, not direct `cargo test`.

Minimum iterative loop:

```text
cd codex-rs
just fmt
just test -p codex-skills-extension
just test -p codex-core-skills
just fix -p codex-skills-extension
git diff --check
```

Add affected `codex-core`, app-server, protocol, config, and TUI checks as changes require.

Before final submission:

- full required package tests;
- benchmark at 10/100/1k/5k/10k entries;
- 200-case routing corpus;
- integration prompt snapshots;
- `just argument-comment-lint`;
- config schema generation when applicable;
- Bazel lock update when applicable;
- full `just test` under maintainer/user workflow;
- acceptance report.

Do not rerun tests after final `fix`/`fmt` if repository instructions say not to.

## Required output from the coding assistant

At completion provide:

1. branch/commit stack;
2. changed-file summary;
3. requirement coverage table;
4. test commands and results;
5. benchmark results;
6. prompt/context snapshots;
7. shadow comparison;
8. security review checklist;
9. config/protocol compatibility note;
10. rollback instructions;
11. remaining failures, if any.

Do not say “complete” while any mandatory requirement/test is missing.

## Upstream communication

When preparing an issue or PR:

- state that the July 12 overflow-only proposal is superseded;
- reference merged PRs #32761, #32768, and #32780;
- state that the patch completes the existing shadow direction;
- reference unmerged PRs only as prior art;
- distinguish implemented behavior from proposed behavior;
- request maintainer validation of fleet metrics;
- avoid claiming that an auto-closed PR was technically rejected;
- avoid claiming merge approval.

## Stop conditions

Stop implementation and report exact evidence when:

- current `main` already implements a requirement differently and incompatibly;
- source authority cannot be preserved;
- a protocol change would break persisted clients without migration;
- a hard context limit cannot be met;
- tests reveal explicit selection regression;
- disabled or hidden skills leak;
- the same step can read through a different generation;
- upstream contribution policy disallows the intended submission path.

Do not work around these conditions by weakening the specification. Update the decision record only
with evidence and reviewer approval.
