# ADR: ChatGPT-operated coding workspace — candidate selection, not production approval

**Date:** 2026-10-11
**Scope:** Only `Binilts03/Public`. Evaluation code and evidence reside on `experiments/chatgpt-workspace-qualification`; do not merge without authorization.

## Non-negotiable goal

A regular ChatGPT conversation must be able to perform the same *outcome and verification* as the owner's Codex coding workflow: explore the true code, use versioned skills and applicable repository instructions, edit in isolated Git worktrees, run real commands/tests, debug failing cases, recover from interruption, preserve evidence and perform genuine independent review where required. A shell tool or successful unit tests alone do not establish parity. ChatGPT does not acquire a native independent model-driven subagent simply because an MCP tool can start processes.

## Evaluated alternatives (source-pinned; read-only third-party checkouts)

| Candidate | Revision | Actual test evidence | Relevant limitations |
|---|---|---|---|
| [MarcoCaamal/workspace-mcp](https://github.com/MarcoCaamal/workspace-mcp/tree/36c9af51c076d2e31517137ab202983dcc52681d) | `36c9af51` | [Public CI 38148844689](https://github.com/Binilts03/Public/actions/runs/38148844689): 403 upstream tests, 15 independently checked stdio/file/coding/skill gates, 7 HTTP/bearer checks PASS | Built-in session memory but process-local job IDs lost after restart; upstream author-specific instructions contaminate MCP bootstrap; bearer is not a full OAuth plugin integration |
| [fwerkor/local-shell-mcp](https://github.com/fwerkor/local-shell-mcp/tree/dec01b9f50f966097ddfc84d357d12a52f238935) | `dec01b9f`, package 5.1.2 | [Public CI 38152260892](https://github.com/Binilts03/Public/actions/runs/38152260892): 84 upstream OAuth/security/skill/recovery tests, 7 independent tool/coding/skill/session tests PASS; [Public CI 38152557755](https://github.com/Binilts03/Public/actions/runs/38152557755): restricted OAuth MCP configuration and authenticated local HTTP initialization PASS | Upstream suite is selective (84 tests, not entire repo); no real public plugin connection or OS sandbox proven; defaults need hardening |
| [hoangcoderr/chatgpt-local-coder](https://github.com/hoangcoderr/chatgpt-local-coder/tree/bc2ce5e6cb12fac20633065fb122fabbbb5c98c3) | `bc2ce5e` | [Public CI 38152260892](https://github.com/Binilts03/Public/actions/runs/38152260892): upstream build/test PASS, independent source assessment confirms open access | `src/lib/path-security.ts` treats project root as default cwd, not an access boundary; `src/lib/permissions.ts` allows arbitrary paths/commands. Reject for direct connection to valuable repos |
| [desktop-commander/remote-desktop-commander](https://github.com/desktop-commander/remote-desktop-commander/tree/b480501dcca59f802ebaf97f2f57b45252d0b720) | `b480501` | Read-only source/docs review, **no live functional test** | Hosted OAuth relay with device agent, but server implementation is proprietary, the device agent must be online and acts with that OS user's permissions. Useful fallback, not self-hostable OSS control plane |

The failed CI runs and intermediate test-adapter mistakes remain visible in Actions history. They are not erased from evidence. In particular, `CallToolResult` on rejected tools differed from success result shape and our independent probe required correction before PASS. The OAuth HTTP test also initially returned **421 Invalid Host** because its TestClient host differed from the configured public origin. The corrected test kept Host validation enabled.

## Provisional decision

**Prefer local-shell-mcp as the executor candidate; retain workspace-mcp as the lower-complexity fallback.** Do not vendor, fork, merge or install on a real host yet.

Reason: local-shell-mcp has *implemented and runtime-verified* skill discovery/read, shell and file operations, real RED–GREEN coding repair, durable logical task state, OAuth metadata/authenticated MCP HTTP and security/recovery regression coverage. A standalone binary or Python/pipx installation is documented, so Docker and Playwright browser binaries are not prerequisites for baseline coding; project-specific tasks may still need them.

This is a PROVISIONAL choice until actual normal ChatGPT plugin invocation and a paired Codex-outcome benchmark pass.

## Security and deployment profile

See [restricted environment template](../research/chatgpt-workspace-qualification/local-shell-mcp.env.example).

Required protections:
- Server bound to loopback behind authenticated HTTPS or a supported Secure MCP Tunnel.
- OAuth enabled, all localhost bypasses disabled, strict Host validation maintained, protected-resource metadata available; no static token in URL.
- Run a separate non-root Linux account inside a dedicated VM or OS-enforced sandbox; don't mount a Docker socket, root filesystem, other repositories or credentials into the execution account.
- Explicitly disable default-enabled remote worker features, GUI and full-container mode for first deployment. Narrow tool access/approval via the plugin and operator.
- Keep skill sources version-pinned, and load exact `SKILL.md` bodies/references rather than summaries. Project instructions (`AGENTS.md` etc.) still require explicit bootstrap and verification.
- Maintain a durable evidence ledger (command, exit code, SHA, skill digests, changes, test outputs); do not count a disconnected job as successful. External model-driven subagents need independently available models and are not included in the minimal baseline.
- Use only a disposable worktree of `Binilts03/Public` for the first write-enabled ChatGPT test. Protected main branch must be unchanged and PR/merge prohibited without approval.

Verified upstream defaults requiring attention:
- `remote_enabled = True`, `auth_bypass_localhost = True`, `oauth_access_token_ttl_s = 0` (no expiry), `host = 0.0.0.0` in [settings source](https://github.com/fwerkor/local-shell-mcp/blob/dec01b9f50f966097ddfc84d357d12a52f238935/src/local_shell_mcp/settings.py).
- The [security policy](https://github.com/fwerkor/local-shell-mcp/blob/dec01b9f50f966097ddfc84d357d12a52f238935/SECURITY.md) explicitly advises running in a disposable container or VM and never mounting host root/Docker socket.

## Remaining qualification gates

1. **H1 — Durable host, isolated permissions:** obtain a Linux runtime that persists filesystem and tasks between chats. Prove clean rebuild, restart, isolation and no cross-repository access; no host provider is selected by this ADR.
2. **H2 — Real HTTPS OAuth:** complete *browser* authorization code + PKCE through deployed proxy/tunnel; verify token rotation/expiry/Host restrictions and no tool access before authorization. Existing in-process synthetic JWT gate is NOT this test.
3. **H3 — Actual normal-chat custom plugin:** install it in the user's account, successfully call read-only tools from a normal ChatGPT conversation (not Work), then turn on limited writes for only Public fixture.
4. **H4 — Skills fidelity and quality:** import actual allowed skill roots and project instructions, verify revisions/resources, execute representative paired repairs/refactors/harness evals under identical frozen baselines, compare outputs and verification evidence against the owner's Codex workflow.
5. **H5 — Failure/recovery and adversarial tests:** crash/restart during live jobs, network loss, bad patch, prompt injection, symlink/TOCTOU, race writes, credential attempts, protected branches and interrupted PRs. Record executed versus static results. Explicitly reject unsafe command paths via the host's OS permissions rather than relying on tool annotations.
6. **H6 — Independent reviews:** preserve genuine independent reviewer tooling when model/provider entitlements exist; otherwise mark its gate unfulfilled instead of simulating a subagent.

No external persistent host, custom ChatGPT plugin or personal account authorization has been created through this evaluation. Those are the remaining external dependencies for a live demonstration.

## Minimum verified baseline runtime

`local-shell-mcp` supports Python >=3.11 and native standalone binaries; its [Python runtime guide](https://github.com/fwerkor/local-shell-mcp/blob/dec01b9f50f966097ddfc84d357d12a52f238935/docs/installation/python.md) and [binary guide](https://github.com/fwerkor/local-shell-mcp/blob/dec01b9f50f966097ddfc84d357d12a52f238935/docs/installation/binary.md) are first-party references. A host still needs Git, language runtimes and command-line toolchains selected by task. Docker is optional; Python package dependencies include the Playwright Python package, but installing browser binaries is task-dependent. No minimum RAM/CPU claim has yet been benchmarked.

## Safety scope

This ADR and its CI changes affect only `Binilts03/Public` on the isolated qualification branch. Pinned upstream projects are fetched read-only by GitHub-hosted disposable runners. The Public main branch remains protected by the workflow policy of **no merge or push to main without explicit authorization**.
