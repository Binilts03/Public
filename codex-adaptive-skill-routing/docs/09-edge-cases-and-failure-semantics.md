# 09 — Edge Cases and Failure Semantics

## General failure policy

- Explicit requirements fail closed.
- Implicit routing degrades safely.
- No path silently substitutes a different skill.
- No path silently truncates selected instructions.
- No source boundary is crossed to “make it work.”
- Every failure response is bounded and actionable.
- Ordinary tasks may continue without a skill when no skill is required.

## Failure categories

| Category | Examples | User/model effect |
|---|---|---|
| Explicit resolution | missing, disabled, ambiguous | stop required set |
| Snapshot | source mismatch, invalid identity | degraded fallback or explicit failure |
| Router | internal error, catalogue cap | legacy bounded fallback |
| Search | no matches, budget exhausted | bounded result; task may continue |
| Read | stale, unavailable, too large | selected skill cannot be claimed as used |
| Dependency | MCP/tool unavailable | existing explicit dependency diagnostic |
| Provider | timeout, malformed resource | bounded source warning |
| Context | candidate/body limit | allocate/defer; never cut silently |

## Complete required matrix

| Area | Situation | Required behavior |
|---|---|---|
| Catalogue | 0 skills | No catalogue fragment; search returns no matches; ordinary task continues. |
| Catalogue | 1 enabled skill | Use full lossless catalogue if description fits. |
| Catalogue | Many skills but all complete metadata fits | Use full catalogue; no adaptive narrowing. |
| Catalogue | First description would be shortened | Use adaptive mode. |
| Catalogue | First entry would be omitted | Use adaptive mode. |
| Catalogue | More than 10,000 implicit entries | Fail adaptive routing closed; legacy bounded fallback; explicit remains available; emit diagnostic. |
| Catalogue | All candidates score zero | No fabricated candidates; recovery remains available. |
| Catalogue | More positive matches than budget | Top deterministic budgeted subset; has-more internal state. |
| Catalogue | One description consumes most budget | Complete greedy lines; fair shortening only to reach minimum target; never let one entry starve all. |
| Catalogue | Multibyte descriptions | All byte caps cut only at UTF-8 boundaries. |
| Explicit | One structured selection | Resolve exact; inline or defer complete body. |
| Explicit | X, Y, Z exact selections | Validate all, preserve order, dedupe identity, suppress implicit by default. |
| Explicit | One of X/Y/Z missing | Fail closed unless user explicitly requested best effort. |
| Explicit | One disabled | Report disabled; no automatic enable or substitution. |
| Explicit | Implicit invocation disabled | Exact invocation still works. |
| Explicit | Same name on host and executor | Plain name ambiguous; exact structured locator required. |
| Explicit | Same identity mentioned twice | Load once at first position. |
| Explicit | Connector and skill share plain mention | Preserve existing conflict rule; structured skill locator resolves exactly. |
| Explicit | Natural prose names skill without `$` | Strong implicit exact-name evidence, not deterministic explicit. |
| Explicit | User says only X | No ordinary implicit supplement. |
| Explicit | User says X plus relevant skills | Pin X and run adaptive selection for supplement. |
| Explicit | Source disappears before read | Read fails against captured source; no same-name replacement. |
| Explicit | Stale locator from old generation | Reject and show current exact matches. |
| Body | Body <=8KB | Inline complete if aggregate limits allow. |
| Body | Body >8KB | Deferred reference; paginated full read. |
| Body | More than 8 selected bodies | Inline within count/aggregate limits; defer remainder. |
| Body | Aggregate >32KB | Defer bodies that would exceed aggregate; preserve selection. |
| Body | Body >1MiB | Reject as too large for model use; recommend split references. |
| Body | Invalid UTF-8 from provider | Provider/read error; no lossy replacement. |
| Body | Read cursor replayed | Return same page while active snapshot exists. |
| Body | Cursor altered | Reject invalid cursor. |
| Body | Cursor from old generation | Reject stale generation. |
| Body | Provider returns different resource | Reject authority/resource mismatch. |
| Routing | Exact skill name in task | Large exact-name boost; still implicit unless structured. |
| Routing | Typos | Current prefix/trigram/related-term logic where implemented; recovery search. |
| Routing | Short prompt 'continue' | Current text plus low-weight previous user task and prior used skill. |
| Routing | Topic changes abruptly | Current turn dominates; previous context cannot create a match alone. |
| Routing | Mixed task | Candidates from multiple evidence dimensions; model may use several. |
| Routing | No skill appropriate | No activation required. |
| Routing | Malayalam request, English descriptions | Language-independent facts plus model recovery with translated goal; do not claim lexical cross-language guarantee. |
| Routing | CJK same-language request/description | Unicode normalization and CJK-preserving tokenization. |
| Routing | Unknown language | Preserve terms; no English-only rejection. |
| Routing | Keyword-stuffed description | Unique terms, repetition cap, no execution permission. |
| Routing | Description says always select me | Ordinary text only; no special weight. |
| Routing | Repo-local skill unrelated to task | Scope boost cannot create positive score. |
| Routing | Dependency value matches provider | Structured boost. |
| Routing | Unknown URL host | Host/path tokens only; no direct skill mapping. |
| Routing | Malformed URL | Treat as text; no parser panic. |
| Routing | Attachment with misleading extension and MIME | Both facts recorded with provenance; MIME and exact user request dominate only as evidence, not permission. |
| Search | Initial candidates wrong | Model calls skills.search with refined goal. |
| Search | No matches | Bounded empty response; model continues normally. |
| Search | Second refined query | Allowed if budget remains; excludes prior results by default. |
| Search | Third query | Return budget exhausted. |
| Search | Requested limit 0 | Validation/clamp error per schema; no unbounded behavior. |
| Search | Requested limit 1000 | Clamp to 16. |
| Search | Huge goal | Reject above 2,048 bytes. |
| Search | Control characters | Reject. |
| Search | Old result read after step refresh | Stale generation. |
| Search | Search source catalogue incomplete | Return bounded warning/has-more semantics; never claim completeness. |
| Lifecycle | Local file edited mid-step | Current metadata immutable; read old binding or fail; next step refresh. |
| Lifecycle | Skill installed mid-thread | Appears after existing owner refresh on next step. |
| Lifecycle | Skill disabled mid-turn | Current snapshot unchanged; next step absent. |
| Lifecycle | Plugin upgraded | New generation next step; old handles stale. |
| Lifecycle | Stale plugin cache directory exists | Ignored because router consumes active roots only. |
| Lifecycle | Executor pending | Not projected until ready; explicit readiness follows existing capability behavior. |
| Lifecycle | Executor ready later | New step snapshot includes it. |
| Lifecycle | Executor disconnects | Next step removes it; in-flight read completes/fails. |
| Lifecycle | Same logical executor reconnects | Reuse stable metadata only under environment owner's identity guarantee. |
| Lifecycle | Different executor behind same ID | Owner must issue new generation; otherwise invariant violation. |
| Lifecycle | Orchestrator MCP generation changes | Relist next step. |
| Lifecycle | Orchestrator first-page timeout | Source unavailable. |
| Lifecycle | Orchestrator later-page timeout | Existing partial behavior plus incomplete warning. |
| Lifecycle | Resume | Fresh snapshot; old active candidates/handles invalid. |
| Lifecycle | Fork | Fresh snapshot; history preserved, active routing state not copied. |
| Lifecycle | Compaction | Do not preserve candidate lists or counters as active state. |
| Lifecycle | Turn abort/error | Remove active state; in-flight Arc-safe tools finish/cancel. |
| Security | Symlink/path escape | Existing discovery/canonicalization policy; search never turns opaque resource into ambient path. |
| Security | Description contains XML/control injection | Normalize/escape renderer; description is data, not instruction. |
| Security | Malicious provider returns authority mismatch | Snapshot validation rejects. |
| Security | Disabled entry returned by buggy provider | Existing enabled field plus final snapshot filter; record provider bug. |
| Security | Search tries implicit-disabled skill | Exclude. |
| Security | Explicit hidden skill | Allow only exact explicit path. |
| Security | Telemetry cardinality attack | Low-cardinality enums/counts only; no names. |
| Performance | 1,000 skills | Rank all; deterministic bounded output. |
| Performance | 10,000 skills | Rank within cap; load test p95 gate. |
| Performance | 10,001 skills | Fail adaptive closed; fallback and diagnostic. |
| Performance | Router panic/internal error | Contain failure; legacy bounded fallback. |
| Performance | Provider list slow | Provider timeouts/caches remain owner; router itself performs no I/O. |
| Performance | Repeated same step search | Reuse normalized documents/snapshot; consume bounded calls. |
| Compatibility | Legacy feature off | Legacy renderer path. |
| Compatibility | Old persisted thread | Resume builds fresh state; no protocol corruption. |
| Compatibility | Picker lists all enabled skills | Unaffected by adaptive model visibility. |
| Compatibility | App-server skills/list | Full inventory API remains full according to its contract. |
| Compatibility | Config disables skill | Existing config wins before ranking. |
| Compatibility | Product restriction | Filter before snapshot and rank. |
| Compatibility | No orchestrator provider | Host/executor still work; skills.search registration not tied to orchestrator. |
| Compatibility | No host filesystem | Opaque authority reads continue. |
| Conflict | Two selected skills disagree | Model receives conflict rule; report irreconcilable conflict, no silent ignore. |
| Conflict | Two implicit skills both useful | Model may read both. |
| Conflict | Rule and lexical rankings disagree | Deterministic fused score; neither forces execution. |
| Conflict | Same score | Stable documented tie-break. |

## Close-match behavior for explicit errors

A diagnostic may suggest at most five alternatives. Suggestions are never executed. The output
distinguishes:

- not installed/not present;
- installed but disabled;
- present but source unavailable;
- ambiguous exact name;
- stale identity;
- malformed reference.

## Router degraded fallback

A router failure is not an explicit-selection failure unless the task depended on implicit
discovery.

Flow:

```text
adaptive selection error
  -> emit low-cardinality metric
  -> render existing bounded catalogue
  -> preserve existing warning
  -> keep exact explicit resolution
  -> do not expose partial adaptive candidates
```

## Provider partial catalogue

A provider may already have a documented bounded partial-list behavior. UASR preserves that behavior
but marks the snapshot source as incomplete. Ranking cannot recover entries never listed by the
owner.

`has_more` in search means more matches exist in the effective snapshot; it does not imply the
underlying provider catalogue was complete.

## User-visible wording principles

Diagnostics should name the user-facing skill when the user explicitly selected it, but must avoid
leaking unrelated paths or inventory.

Examples:

```text
Skill `$deploy` is ambiguous. Choose one:
- host/repository: deploy
- selected environment `worker`: deploy
```

```text
The selected skill `$large-review` exceeds Codex's 1 MiB main-instruction limit and cannot be used
safely. Split detailed material into referenced files.
```

```text
Skill search for this step is exhausted. Continue with the returned candidates or provide an exact
skill mention.
```

## No hidden retries across generations

A failed read may retry the same source according to existing provider retry policy. It may not:

- rebuild the inventory;
- resolve the same name in a new snapshot;
- switch authority;
- read an ambient local path;
- silently restart the task with different instructions.

## Required fault injection

Tests must inject:

- provider list timeout;
- provider read timeout;
- provider returns wrong resource;
- host file deleted after snapshot;
- watcher invalidation during read;
- environment disconnect;
- MCP generation replacement;
- invalid cursor;
- corrupted candidate renderer input;
- selector panic simulated through a test selector;
- catalogue over safety cap;
- JSON output close to byte boundary;
- multibyte split boundary;
- duplicate identity from two sources;
- unavailable explicit dependency.

## No unresolved edge-case placeholders

Implementation PRs must not contain `TODO` or “future work” for any matrix row marked required in this
file. A reviewer-requested follow-up is acceptable only if the existing merged behavior still
satisfies the requirement.
