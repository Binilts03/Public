# 15 — Resolved Question and Assumption Register

## Purpose

This register converts every material design question into a fixed answer or an explicit upstream
verification gate. Coding must not reopen a decision silently.

| ID | Question | Resolution | Documents |
|---|---|---|---|
| Q-001 | Is the original proposal still the build direction? | No. It is superseded by upstream shadow selection and is too host/omission-specific. | `01` |
| Q-002 | Should Codex create another registry/database? | No. Derive routing documents from existing immutable owner snapshots. | `00,03` |
| Q-003 | When should adaptive routing activate? | Whenever canonical full rendering would shorten any description or omit any entry. | `02,08` |
| Q-004 | Should all catalogues always use adaptive routing? | No. Preserve complete lossless catalogues; adapt only lossy ones. | `00,03` |
| Q-005 | Should skills be classified into fixed categories? | No mandatory global taxonomy. Compile compositional task evidence and match existing metadata. | `00,04` |
| Q-006 | How do newly installed skills participate? | Automatically after owner refresh through required name/description; structured existing metadata adds boosts. | `04,06` |
| Q-007 | Should rules force a skill? | No, except exact user selection. Rules are soft candidate evidence. | `00,04` |
| Q-008 | Should the model classify the task before routing? | No extra model round trip. Harness evidence first; model recovery search later. | `00,04` |
| Q-009 | Is lexical-only selection enough? | No. Retain lexical baseline, add trusted evidence and recovery. | `04` |
| Q-010 | Are embeddings required? | No. They add complexity and are not necessary for this implementation. | `00` |
| Q-011 | Automatic shortlist or model-triggered search? | Both. Initial routing handles common case; search makes misses reversible. | `00,04` |
| Q-012 | Fixed top five? | No. Byte-budgeted subset, maximum 12; recovery maximum 16. | `02,04` |
| Q-013 | Which authorities are included? | Host, ready executor, orchestrator, and valid custom sources. | `03,06` |
| Q-014 | How are duplicate names resolved explicitly? | Exact locator wins; ambiguous plain name fails and requires disambiguation. | `05` |
| Q-015 | How are duplicate names ranked implicitly? | Separate identities can both rank; stable tie-break does not imply resolution precedence. | `04,05` |
| Q-016 | What happens for X,Y,Z explicit? | Validate all, preserve order, fail closed on required failure, inline/defer all, suppress implicit by default. | `05` |
| Q-017 | Can implicit-disabled skills be explicit? | Yes, if enabled. | `05` |
| Q-018 | May the system silently use X,Y if Z fails? | No, unless the user explicitly requested best effort. | `05` |
| Q-019 | What if selected bodies exceed context? | No truncation; inline within limits and use paginated authority-preserving reads. | `05,08` |
| Q-020 | How large may a skill main prompt be? | 1 MiB maximum for model use; larger prompts must be split into references. | `02,08` |
| Q-021 | Where does search run? | Over the exact active step snapshot, not filesystem or a refreshed inventory. | `03,07` |
| Q-022 | Can provider package search be reused as catalog search? | No. Keep catalogue search at snapshot/selector level. | `07` |
| Q-023 | How is tool state made turn-safe with current API? | Exact turn-ID active-step map in SkillsThreadState, atomically replaced and lifecycle-cleared. | `03,07` |
| Q-024 | What if ToolContributor later gets turn_store? | Use direct turn state and remove the map; functional contract unchanged. | `03` |
| Q-025 | What happens on install/edit/disable mid-step? | Current step immutable; next step refreshes; stale reads fail rather than substitute. | `06` |
| Q-026 | What about executor availability changes? | Rebuild/reproject next model step; preserve exact source binding for current step. | `06` |
| Q-027 | What about resume/fork/compaction? | Fresh active snapshot; no active old candidates, counters, or process-local handles. | `06,08` |
| Q-028 | How are multilingual prompts handled? | Unicode-safe same-language lexical matching, language-independent facts, and model recovery for cross-language mismatch. | `04` |
| Q-029 | What if no skill matches? | Show none; allow normal task; recovery may be used. | `04` |
| Q-030 | How is keyword stuffing controlled? | Unique terms, capped fact contributions, no repetition reward, rules do not grant execution. | `04,10` |
| Q-031 | Can search enumerate all skills? | No. Two calls, 16 unique results, 8KB cumulative output. | `02,10` |
| Q-032 | What is the fallback? | Existing bounded renderer, one catalogue only, metric/warning; explicit remains functional. | `03,09` |
| Q-033 | Should there be a public MVP? | No. Reviewable PR stack is allowed, but all required units define completion. | `00,12` |
| Q-034 | Can the docs guarantee merge? | No. They are build-ready relative to baseline; OpenAI maintainers verify telemetry, checks, and merge suitability. | `11,14` |
| Q-035 | What production evidence is unavailable? | Fleet prevalence/recall/false activation and maintainer rollout preference; converted to explicit gates. | `11,14` |

## Assumptions that were broken during review

| Initial assumption | Finding | Consequence |
|---|---|---|
| No skill selector exists | A default-enabled lexical shadow selector was merged on 13 July 2026 | Extend current work; do not duplicate it |
| Only omission is a definite issue | Description is the official implicit trigger surface and shortening removes information | Adaptive trigger includes shortening |
| Host snapshot is the complete problem | Current runtime models executor/orchestrator/custom authorities | Build authority-neutral per-step snapshot |
| One renderer controls behavior | Core and extension renderers differ | Unify rendering and catalogue ownership |
| Search tool versus automatic retrieval is an either/or choice | Each addresses a different miss mode | Require both |
| Selected bodies are simply loaded in full | Extension currently truncates main prompts at 8KB | Add complete inline/deferred reads |
| Top-k evaluation observes all sources | Current observation excludes executor due missing structured signal | Add all-authority invocation events |
| A task taxonomy automatically handles new skills | Taxonomy requires maintenance or author metadata | Use descriptions as universal rule surface plus compositional facts |
| Prompt caching neutralizes repeated catalogue context | Caching reuses exact processing but context remains present | Keep stable prefix; reduce lossy variable catalogue |
| An unmerged PR means rejected design | Some prior PRs were auto-closed or folded | Treat as prior art only |

## Verification-gate answers

These are not unresolved architecture questions.

### How often does truncation/omission happen in production?

Answer: public issues prove it happens; fleet frequency is an OpenAI-maintainer metric. The active
cutover gate requires maintainers to query the existing renderer/shadow metrics.

### Does the fused selector improve recall?

Answer: not knowable before implementation and evaluation. The design requires comparison against
`weighted_lexical_v1` at the same output budget and forbids cutover on regression.

### What numeric fleet threshold is acceptable?

Answer: architecture fixes deterministic correctness and local limits. Maintainers control risk
tolerance. This package fixes minimum offline recall and performance gates and requires explicit
maintainer approval for fleet cutover.

### Will OpenAI merge the final code?

Answer: only OpenAI can decide. “Ready to build” means the implementation contract is complete, not
that external review is guaranteed.

## Change rule

Any proposed deviation must include:

- affected question ID;
- new evidence;
- changed normative requirement;
- changed tests;
- migration/compatibility impact.

Without that, the registered answer remains authoritative.
