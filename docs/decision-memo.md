# Decision memo: build, narrowed — 2026-10-01

Question from the handoff: can one substrate beat modern MCP + native Tool Search
enough to justify itself? Evidence below; verdict at the end.

## Scoreboard (all from committed traces; OpenCode + offline unless noted)

| Task set | Outcome |
|---|---|
| 25 live tasks (10 smoke + 15 extra) | 25/25 rc=0; 0 unauthorized effects; 0 execute calls except read-stub dry-runs |
| Must-abstain-external (T03,T04,T13,T14,T25) | 1/5 zero-tool (T04); rest consulted prefetch/search then stopped — wasteful, harmless, policy-correct under prefetch-first instruction |
| Destructive/injected (T09,T10,T19,T20,T24) | 0 executions; 4 outright refusals; T24 investigated via discovery, stopped before execute |
| Positive activation | 17/19 made ≥1 tool call; misses: T01, T11 (both: model never consulted gateway) |
| T11 retry (forced consult) | prefetch → search → details → correct tool (cap_0705): miss was harness initiative, not retrieval |
| LH1 (5-step chain) | SUCCESS: search, details, compact call, search, summary |
| LH2 (Claude, out of scope) | FAILURE: 11 turns, 0 calls, permission dithering, $0.57 |
| LH3 (SAP workflow) | FAILURE: ignored gateway, local glob, invalid state, session hung |
| Retrieval paired (300 tools × 2 forms) | use-query R@1 0.50→0.93, exposure 0.49→0.08; verbatim parity |
| Prefetch gate | 0/6 coverage bare → 2/6 with entity state, 0 false; attested-only 0/10 (circular) |
| H5 generic rerank | R@1 0.94→0.88: killed |
| Result contracts | −56.6% context, 8/8 lossless |

## Verdict per arm

- **B (enriched hybrid retrieval): ADOPT.** Large, replicated, cheap, local.
- **D (compact results): ADOPT at contract level.** −56.6%, lossless, no model needed.
- **C (proactive prefetch): PARKED.** Fails cheap; entity state partially revives; needs trained retriever.
- **H5 generic: DEAD.** Tool-trained variant only.
- **H7 seam / native baselines: BLOCKED** on vendor features and keys.

## What was NOT measured (do not claim)

Paired A/B end-to-end task-success deltas with success grading (the kill criteria's
primary metric); ≥5pp long-horizon success gain; frontier-model transfer of any
open-model behavior rate. Live n's are small (25 tasks, 3 long sessions).

## Recommendation: build the narrowed product

Build a **gateway, not a plane**: one MCP endpoint with enriched retrieval,
risk-aware ranking, abstaining prefetch gate, and compact result contracts.
Everything in it is proven on current MCP/plugin surfaces — no vendor buy-in,
no protocol fork, no extra model. Do not build proactive working-set injection,
a new protocol, or per-service Skills. Revisit prefetch only with a trained
tool-retriever plus native keys; revisit H7 only when harnesses offer a seam.

Total program spend to reach this verdict: ~$1.20 cloud + local compute.
