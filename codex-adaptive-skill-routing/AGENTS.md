# Coding assistant contract

Implement and verify the complete patch series. Do not reduce it to an
omission-only experiment, a host-only router, a fixed top-five list, a taxonomy,
or a second persistent registry.

Required invariants:

1. Explicit selections bypass discovery and are ordered and atomic.
2. Disabled, ambiguous, missing, stale, or oversized explicit selections fail
   closed; never substitute a similar skill silently.
3. A complete catalogue is used when lossless. Adaptive routing begins on any
   description shortening or omission.
4. The effective per-turn snapshot is authoritative for search and read across
   every authority.
5. Initial candidates do not make misses irreversible; bounded recovery search
   is always available in adaptive mode.
6. Skill instructions and referenced resources are never silently truncated.
7. Only one model-visible catalogue owner is active. Legacy behavior remains the
   failure fallback when the extension is absent.
8. No new runtime dependency, database, watcher, embedding service, or mandatory
   skill taxonomy may be introduced.
9. Do not enable the feature by default until the verification gates in
   `docs/11-verification-and-test-plan.md` pass.

Use the repository's Rust 1.95 toolchain on Linux. Run formatting, targeted tests,
core/app-server checks, and `git diff --check`. Do not install Visual Studio Build
Tools for this project.

