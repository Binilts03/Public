# ChatGPT coding workspace: qualification and connection gate

Date: 2026-10-11.
Target repository: Binilts03/Public ONLY. Main baseline 6ba9bfbe230dc21cea01ad9addbce580ae17ebca; all writes are on experiments/chatgpt-workspace-qualification.

## Evidence: executed

- First run: https://github.com/Binilts03/Public/actions/runs/38147609182
  - Pinned upstream workspace-mcp at 36c9af51c076d2e31517137ab202983dcc52681d built and passed 403 upstream tests.
  - Independent probe: 12 PASS / 2 FAIL due to the probe's argument collision, 1 WARN. These were probe errors, not upstream defects.
- Probe repaired at fae0b9a2a055ee57a855769113395f4fddf3eebf.
- Successful run: https://github.com/Binilts03/Public/actions/runs/38147666297
  - Ubuntu 24.04, Node 22.23.3, Python 3.12.3.
  - Upstream 403 PASS in 20 test files.
  - Independent real MCP probe 14 PASS / 0 FAIL / 0 BLOCKED / 1 WARN.
  - Tested initialize, 36 discovered tools, workspace binding, file read, symlink and path escape rejection, multi-file patch, invalid-patch no-write, git status/diff, actual Node execution, background job/log, skill read, unrelated test fixture unchanged.
  - Artifact: https://github.com/Binilts03/Public/actions/runs/38147666297/artifacts/11705453129

This is black-box tool evidence, not production sandbox evidence or Codex parity.

## Open gates

- Upstream server instructions contain the original maintainer's specific harness stages and skills. Replace before using the user's skills. Observed WARN.
- Executable allowlist is not an OS security sandbox. Production command execution needs an isolated low-privilege process and credible filesystem/network protection. Source-confirmed.
- Background job IDs vanish on server restart. Job recovery/reconciliation is needed. Source-confirmed.
- Patch prevalidation does not guarantee crash-atomic multi-file writes. Source-confirmed.
- No externally reachable persistent MCP endpoint or Secure MCP Tunnel has been configured.
- No custom plugin has been installed or invoked from a normal ChatGPT chat.
- Skill fidelity, independent subagents/reviews, interrupted long-running tasks, and paired real-world Codex comparison remain unverified.

## Connection gate

Official guide: https://developers.openai.com/plugins/deploy/connect-chatgpt
Authentication: https://developers.openai.com/plugins/build/auth
Private tunnel: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels

1. Provision a PRIVATE isolated host and persistent workspace for the backend. Never use a temporary GitHub Actions runner as the permanent coding endpoint.
2. Establish either an HTTPS Streamable HTTP MCP endpoint with suitable OAuth 2.1 authentication, or a Secure MCP Tunnel if available. Upstream static-bearer auth is not a complete OAuth 2.1 solution.
3. In ChatGPT Plugins choose + then Add custom MCP server. Supply MCP /mcp URL or supported tunnel ID; configure authentication and review the discovered tools.
4. Install plugin, create a NEW ORDINARY ChatGPT chat, select the plugin using @. Validate an innocuous read-only call before exposing write or shell tools.
5. Verify tool names, parameters, authorization, output and evidence. Record the actual custom-plugin identifier and version.

This account's tools do not expose server hosting, tunnel provisioning, custom plugin creation, or the user's auth credentials. These actions are not claimed complete.

## Normal-chat C1 acceptance scenario

Read-only: return the configured repository and exact revision, inspect a known fixture, and demonstrate no filesystem write.
Write: create an isolated disposable worktree, patch a file at a pinned base, run a check, return exact exit code and diff, confirm the main branch did not change.
Security: show that out-of-root file access, unapproved writes, and unauthorized command execution are rejected by an independent boundary.
Recovery: start a second ordinary ChatGPT conversation and resume through exact work ID, SHA, skill revision and test evidence.
Quality: a successful MCP tool call is NOT the same as a successful Codex-grade coding task. Paired task evaluations must follow C1.

## Repository safety

No tool may create, update, publish, push, merge or run workflows in any repository other than Binilts03/Public. The qualification workflow only reads pinned upstream open-source code into a disposable GitHub runner. Do not modify Public/main without explicit authorization.
