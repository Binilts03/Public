# Unified Adaptive Skill Routing for Codex

## Status

**Engineering source of truth for implementation and upstream review.**

This document set specifies a complete correction to Codex skill discovery and routing, pinned to
`openai/codex` commit [`8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66`](https://github.com/openai/codex/commit/8b2c84ddccafe40dc0dc09f9f52bcbdc9dc45d66) on
13 July 2026.

It is not a SaaS product specification, a market proposal, or an MVP plan. It is a coding issue
specification intended to be consumed by an implementation agent, reviewed by the Codex team,
validated through the repository's normal checks, and merged only after upstream maintainers accept
the behavior and evidence.

The documents supersede the earlier proposal
[`deferred-skill-discovery-proposal.md`](https://github.com/Binilts03/Public/blob/main/deferred-skill-discovery-proposal.md).
That proposal was a useful intermediate analysis, but it is no longer an accurate implementation
direction because the upstream repository changed on 13 July 2026 and because its scope was limited
to omitted host skills.

## Final direction

The required solution is **Unified Adaptive Skill Routing (UASR)**:

1. Build one immutable, authority-bound effective skill snapshot for each model step.
2. Preserve the existing deterministic explicit-invocation path.
3. Render the complete skill catalogue when it fits without shortening or omission.
4. When the complete catalogue would be lossy, compile the user task and trusted runtime facts into
   routing evidence, rank the full eligible snapshot locally, and expose a bounded task-specific
   candidate catalogue.
5. Keep a bounded `skills.search` recovery tool available so an initial ranking miss is reversible.
6. Provide a uniform authority-preserving `skills.read` path for deferred skills and oversized skill
   instructions.
7. Use the existing weighted lexical selector as the baseline, then augment it with deterministic
   evidence derived from URLs, artifacts, file types, tool dependencies, source identity, scope, and
   bounded conversation continuity.
8. Keep all existing enabled, policy, product, scope, plugin, executor, orchestrator, and trust
   decisions authoritative. The router may narrow model visibility; it must never broaden
   availability.

The complete skill inventory remains in Codex-owned memory. Only a lossless small catalogue or a
bounded relevant subset enters model context.

## Document order

| File | Purpose |
|---|---|
| `00-engineering-decision.md` | Final decision, non-negotiable behavior, and rejected alternatives |
| `01-current-state-and-proposal-critique.md` | Verified current behavior and why the earlier proposal is not correct |
| `02-problem-statement-requirements-invariants.md` | Precise problem, scope, requirements, and invariants |
| `03-system-architecture.md` | Components, data flow, snapshots, and model-step lifecycle |
| `04-routing-engine.md` | Task evidence, lexical scoring, deterministic rules, fusion, budgeting, and recovery |
| `05-explicit-and-multi-skill-semantics.md` | Exact behavior for one or many user-selected skills |
| `06-authority-snapshot-and-lifecycle.md` | Host, executor, orchestrator, custom sources, refresh, install, disable, resume |
| `07-api-and-rust-contracts.md` | Proposed Rust types, tool schemas, limits, and module boundaries |
| `08-context-and-skill-body-loading.md` | Prompt placement, caching, replacement, compaction, and complete reads |
| `09-edge-cases-and-failure-semantics.md` | Required real-world behavior and failure matrix |
| `10-security-and-abuse-resistance.md` | Threat model, trust boundaries, prompt injection, stale handles, and limits |
| `11-verification-and-test-plan.md` | Unit, integration, property, load, compatibility, and shadow evaluation |
| `12-implementation-plan.md` | Complete reviewable change stack, file map, migration, and repository checks |
| `13-requirements-traceability.md` | Requirement-to-design-to-test mapping |
| `14-source-baseline.md` | Primary sources, upstream prior art, issues, and exact baseline |
| `15-resolved-question-register.md` | Fixed answers to all material design questions and broken assumptions |
| `16-coding-assistant-execution-instructions.md` | Operational handoff instructions for the coding assistant |
| `ALL-IN-ONE.md` | Concatenated source of truth for assistants that prefer one file |
| `PACKAGE-AUDIT.md` | Automated consistency and completeness audit |

## Normative language

`MUST`, `MUST NOT`, `SHOULD`, and `MAY` are normative.

No document in this set permits silently dropping an explicitly selected skill, reading a skill
through the wrong authority, exposing disabled skills, or treating routing rank as permission to
execute a skill.

## Baseline drift rule

Before coding begins, compare the pinned baseline with the then-current `main`.

- If the relevant files are unchanged, implement this specification directly.
- If upstream has promoted or replaced the shadow selector, map every requirement in
  `13-requirements-traceability.md` to the new code before editing.
- Do not restore deleted parallel catalogue owners merely to match this file map.
- Upstream behavior and authority boundaries take precedence over file names, but not over the
  functional invariants in this package.

## Definition of implementation complete

Implementation is complete only when:

- every normative requirement is implemented;
- every mandatory test class is present and passing;
- the old and new model-visible catalogue paths cannot both inject duplicate metadata;
- explicit selection parity is demonstrated;
- all authority types are covered;
- lossy catalogue cases use adaptive routing;
- recovery search and deferred full reads work;
- no selected skill body is silently truncated;
- rollback and diagnostics work;
- the repository-required formatting, linting, schema generation, lockfile, and test checks pass;
- upstream maintainers have reviewed any behavioral or protocol changes.

Shadow evaluation is a verification gate, not an optional future phase and not an MVP boundary.
