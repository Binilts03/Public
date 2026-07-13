# 13 — Requirements Traceability

## Purpose

This matrix prevents implementation from being declared complete while a required behavior remains
only prose.

| Requirement | Design owner | Mandatory verification |
|---|---|---|
| REQ-INV-001 | 03 snapshot builder consumes owner catalogues | snapshot test: no filesystem access; fake owner catalogues |
| REQ-INV-002 | 03 immutable SkillRoutingSnapshot per step | lifecycle integration; snapshot Arc immutability |
| REQ-INV-003 | 03/06 authority-bound merged snapshot | host/executor/orchestrator/custom integration |
| REQ-INV-004 | 02/03 implicit view filters | disabled/product/implicit-hidden tests |
| REQ-INV-005 | 05 explicit view | implicit-disabled explicit test |
| REQ-INV-006 | 06 generation identity | stale handle/read tests |
| REQ-MODE-001 | 03 full-render probe | render report integration |
| REQ-MODE-002 | 08 full mode | lossless prompt snapshot |
| REQ-MODE-003 | 04/08 adaptive mode | shortening and omission trigger tests |
| REQ-MODE-004 | 03/09 degraded fallback | fault-injected selector test |
| REQ-EXP-001 | 05 resolver order | structured/path/$/locator tests |
| REQ-EXP-002 | 05 ordered multi-skill set | X/Y/Z order/dedupe test |
| REQ-EXP-003 | 05 fail/no substitution | missing/disabled/ambiguous/stale tests |
| REQ-EXP-004 | 05 partial failure policy | no model request on required failure |
| REQ-EXP-005 | 05 closed set | closed-set candidate suppression |
| REQ-EXP-006 | 05 open set | pinned plus adaptive candidates |
| REQ-IMP-001 | 04 full eligible rank | 10k corpus test; no first-1000 truncation |
| REQ-IMP-002 | 04 lexical baseline | existing weighted_lexical_v1 tests |
| REQ-IMP-003 | 04 evidence boosts | fused selector tests |
| REQ-IMP-004 | 04 evidence model | URL/MIME/extension/dependency/continuity tests |
| REQ-IMP-005 | 04 stable sort | randomized input-order property test |
| REQ-IMP-006 | 04 allocator | count/byte boundary tests |
| REQ-IMP-007 | 03/07 identity-preserving candidates | search/read identity test |
| REQ-IMP-008 | 06 install lifecycle | install then next-step discovery integration |
| REQ-REC-001 | 04/07 skills.search | tool registration and schema test |
| REQ-REC-002 | 03/07 active step snapshot | stale generation and source-change tests |
| REQ-REC-003 | 04 exclude semantics | already-visible/result exclusion test |
| REQ-REC-004 | 02/04 budgets | two-call/16-result/8KB tests |
| REQ-REC-005 | 07 uniform read | all-authority search/read test |
| REQ-REC-006 | 04 no-match | empty bounded output test |
| REQ-READ-001 | 05/08 no silent truncation | oversized body prompt snapshot |
| REQ-READ-002 | 08 inline path | 8KB/32KB/count tests |
| REQ-READ-003 | 08 deferred reference | aggregate overflow test |
| REQ-READ-004 | 07/08 pagination | exact reassembly property test |
| REQ-READ-005 | 07 authority-neutral read | host/executor/orchestrator/custom read tests |
| REQ-READ-006 | 08 required-read guidance | context snapshot and model sequence test |
| REQ-LIFE-001 | 06 step immutability | file/config change during step |
| REQ-LIFE-002 | 06 next-step refresh | watcher/plugin/executor/orchestrator refresh tests |
| REQ-LIFE-003 | 06 unavailability projection | executor disconnect integration |
| REQ-LIFE-004 | 06 resume/fork | resume/fork integration |
| REQ-LIFE-005 | 06/08 compaction | candidate state recomputation test |
| REQ-OBS-001 | 11 shadow comparison | metrics method comparison |
| REQ-OBS-002 | 11 mode metrics | metric dimension assertions |
| REQ-OBS-003 | 11 structured invocation | all authority invocation tests |
| REQ-OBS-004 | 10 privacy | telemetry snapshot review |
| REQ-COMP-001 | 00/04 no schema requirement | existing skill fixture tests |
| REQ-COMP-002 | 02 picker/list unaffected | app-server and TUI tests |
| REQ-COMP-003 | 05 policy compatibility | explicit hidden test |
| REQ-COMP-004 | 06/11 replay compatibility | persisted rollout tests |
| REQ-COMP-005 | 03/12 rollback | off/shadow/active config tests |
| REQ-NF-001 | 02/08 hard limits | property tests for every fragment/output |
| REQ-NF-002 | 04 local selector | benchmark and no-I/O test |
| REQ-NF-003 | 03 snapshot-derived docs | memory/lifecycle tests |
| REQ-NF-004 | 03/06 authority portability | remote/no-host integration |
| REQ-NF-005 | 07/12 module layout | code review/static inspection |
| REQ-NF-006 | 04 stable keys | determinism property test |
| REQ-NF-007 | 10 telemetry privacy | metric attribute audit |

## Cross-cutting edge-case traceability

| Edge group | Normative document | Test location/type |
|---|---|---|
| Explicit one/many/missing/disabled/ambiguous | `05` | extension + core integration |
| Body size/pagination/cursor | `05`, `07`, `08` | unit property + integration |
| Short/referential/mixed/no-skill | `04`, `09` | benchmark + integration |
| Multilingual and Unicode | `04`, `09`, `10` | selector unit + benchmark + fuzz |
| Install/edit/disable/remove/upgrade | `06`, `09` | app-server lifecycle integration |
| Executor ready/disconnect/reconnect | `06` | remote environment integration |
| Orchestrator timeout/generation | `06` | fake MCP provider integration |
| Resume/fork/compaction | `06`, `08` | core persisted-thread integration |
| Malicious metadata/keyword stuffing | `04`, `10` | adversarial benchmark + unit |
| Catalogue explosion/performance | `02`, `11` | load benchmark + fallback test |
| Duplicate catalogue ownership | `03`, `08` | exact request snapshot |
| Rollback/config compatibility | `12` | mode/config/schema integration |

## Pull-request checklist

Every PR in the required stack must state which requirement IDs it:

- implements;
- tests;
- intentionally leaves to a later dependent PR.

The final PR/acceptance report must show no remaining required IDs.

## Change-control rule

If implementation changes a normative behavior, update:

1. the owning document;
2. this matrix;
3. the relevant edge-case row;
4. the corresponding test.

Do not change a limit or precedence rule only in code.
