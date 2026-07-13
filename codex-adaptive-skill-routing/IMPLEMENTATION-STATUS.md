# Implementation status

Baseline: `openai/codex@c7a4a7e136d96554e1fc6f66532e6060fd2aaf15`.

## Completed in the patch series

- shared cross-authority renderer and render-loss report;
- loss-triggered shortlist activation;
- merged immutable turn catalogue and lifecycle binding;
- source, scope, plugin, dependency, artifact, typo, multilingual, and continuity
  evidence;
- explicit ambiguity and multi-skill atomicity;
- bounded `skills.search`, paginated `skills.list`, and paginated `skills.read`;
- recovery/search/body/context bounds and stale-turn failure behavior;
- feature flag, tracing, and focused unit/integration tests.

## Verification evidence

- `rustfmt` parses and formats every changed Rust file;
- `cargo metadata --no-deps --format-version 1` passes;
- `git diff --check` passes;
- the patch series applies cleanly to the pinned baseline;
- Linux CI reached the changed crates; compiler findings are retained as the
  small `0004` follow-up patch rather than rewriting review history;
- selector findings are retained as the small `0005` follow-up patch, which
  rejects incidental n-gram overlap while preserving typo and CJK recovery;
- an integration test exposed executor-catalog leakage into the legacy shadow
  experiment; `0006` confines authority merging to adaptive-routing turns;
- the complete extension suite refined that boundary: `0007` keeps the merged
  catalogue available for explicit resolution, filters it only for the legacy
  shadow prompt, and limits explicit-catalog suppression to adaptive mode;
- local `cargo check` reached Rust compilation but cannot link procedural macro
  build scripts because this Windows host intentionally has neither MSVC Build
  Tools nor Windows SDK import libraries;
- Docker Desktop's Linux image API returned HTTP 500, so no claim of passing
  Linux tests is made locally.

The GitHub Actions workflow is the executable verification boundary. A coding
assistant must not report the implementation as merge-ready until that workflow
and the upstream gates in `docs/11-verification-and-test-plan.md` pass.

## Intentional non-changes

- no persistent skill index;
- no central classification taxonomy;
- no embeddings;
- no installer or environment mutation;
- no default activation before evidence gates;
- no change to the `SKILL.md` format.
