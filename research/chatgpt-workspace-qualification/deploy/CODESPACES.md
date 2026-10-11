# Codespaces private MCP connection gate (qualification only)

This path uses `Binilts03/Public` on `experiments/chatgpt-workspace-qualification`. It is NOT the dedicated-VM systemd installer and is NOT production hosting.

## Evidence already observed from Codespace

- Codespace repository, remote and branch verified; worktree clean at `422ebb9`.
- Managed Python 3.12.15 and pinned `local-shell-mcp` commit `dec01b9f50f966097ddfc84d357d12a52f238935` installed in a user staging directory.
- Independent in-process conformance: 7 PASS / 0 FAIL, including red-green code repair and denied traversal.
- Does not establish persistent security boundary or remote ChatGPT connectivity.

## Two distinct privileged deployment stages

1. `codespaces-isolated-stage.sh` (run with `sudo bash`) creates `chatgpt-controller` and `chatgpt-worker` UIDs, a root-owned Python 3.12 runtime, a Public-only detached Git worktree without a usable push URL, and private OAuth secrets. It **does not start anything**. It refuses to overwrite a prior or partially created layout.
2. `codespaces-start-controller.sh "$CODESPACE_NAME"` (run with `sudo bash`) sets the expected Codespaces HTTPS origin, starts the controller **without the worker**, verifies OAuth metadata and PKCE S256, and rejects unauthenticated MCP initialize with HTTP 401. It makes **no port visibility changes**.

These scripts have their own CI syntax/static-contract tests. They have not yet been executed on this Codespace or been established as secure on this host. Review the scripts and the outcome before exposing a port.

## Operator commands

From the Codespace shell, **not from inside a sourced script**:

```bash
cd /workspaces/Public
git pull --ff-only origin experiments/chatgpt-workspace-qualification
bash -n research/chatgpt-workspace-qualification/deploy/codespaces-isolated-stage.sh
bash -n research/chatgpt-workspace-qualification/deploy/codespaces-start-controller.sh
sudo bash research/chatgpt-workspace-qualification/deploy/codespaces-isolated-stage.sh
sudo bash research/chatgpt-workspace-qualification/deploy/codespaces-start-controller.sh "$CODESPACE_NAME"
```

Success requires both `ISOLATION_STAGED_PASS` and `LOCAL_CONTROLLER_GATE_PASS`. If a script fails, stop and capture non-secret output. Do not remove directories or recreate users without an audit, and never print the OAuth signing secret.

## Recover an interrupted Stage 2 (existing Codespace)

A real Codespaces run installed both Linux users, the privileged Python runtime, and the worker's Public-only detached worktree, then **blocked because the worker could write to /workspaces/Public**. This is a genuine boundary failure. **Do not rerun the blank-host installer** after it has created users and state, and do not delete, reclone, or regenerate OAuth credentials.

Review the dedicated recovery script before execution. It requires the standard Linux POSIX ACL utilities (Ubuntu package `acl`); install those tools if missing. On a host where the Codespaces workspace mount does not support per-user ACLs, the script refuses to qualify rather than weakening isolation.

```bash
cd /workspaces/Public
git pull --ff-only origin experiments/chatgpt-workspace-qualification
command -v setfacl >/dev/null && command -v getfacl >/dev/null || sudo apt-get install -y acl
bash -n research/chatgpt-workspace-qualification/deploy/codespaces-qualify-partial.sh
sudo bash research/chatgpt-workspace-qualification/deploy/codespaces-qualify-partial.sh
```

This checks the existing credentials without displaying them; checks the worker's pinned Git remote, detached worktree and disabled push; verifies both users' Linux permissions and Docker socket access; saves the existing worktree-root ACL privately and adds only a `chatgpt-worker` deny entry to `/workspaces/Public`; then verifies the Codespace owner still has access and the Git worktree remains clean. It issues a root-only qualification marker only after all checks pass. It does not start a listener or expose a forwarded port. If it stops with `BLOCKED`, inspect before changing anything. The controller launcher also rechecks this boundary at every start.

After **`PARTIAL_STAGE_RECOVERED_PASS`** only:

```bash
sudo bash research/chatgpt-workspace-qualification/deploy/codespaces-start-controller.sh "$CODESPACE_NAME"
```

Do **not** make port 8765 public as part of this step. Even a clean ACL denial on /workspaces/Public does not itself prove complete host sandboxing, job supervision, or ordinary ChatGPT tool execution.

## Public ingress is an additional user-controlled security gate

Do **not** make Codespaces port 8765 public until the two results above and a host-identity review pass. GitHub's private forwarded-port authentication is not automatically compatible with ChatGPT's MCP OAuth client. A public forwarded port has no GitHub authentication; rely on the MCP OAuth boundary only after external discovery/authentication/negative tests succeed.

When explicitly approved for the isolated-controller-only test:

- In Codespaces PORTS, confirm `8765` is forwarded. Verify the URL equals `https://<codespace-name>-8765.app.github.dev` and the OAuth issuer from that URL matches the server configuration.
- Changing visibility to **Public** is a consequential exposure action performed by the operator in Codespaces. Do not automate it as part of staging.
- Test external `GET /.well-known/oauth-authorization-server` and `/.well-known/oauth-protected-resource`; require HTTPS issuer and PKCE S256.
- An unauthenticated `POST /mcp` must return 401. A wrong bearer must also return 401; authorized authorization-code PKCE login and MCP initialization must succeed.
- The private controller admin PIN is in `/srv/chatgpt-controller/controller.env`; do not paste it into ChatGPT, this repository, a GitHub Actions log or a public message. Enter it only in the trusted OAuth consent prompt; verify its origin.
- Install through [OpenAI's custom MCP connection flow](https://developers.openai.com/plugins/deploy/connect-chatgpt), then invoke the plugin from a **new ordinary ChatGPT conversation**. Record tool IDs and responses, not tokens.

## Remaining gates

- A live Codespaces host test of separate Linux UIDs, credential unreadability and worker access controls.
- Enrollment of the low-privilege Public-only worker and remote execution with exact file/worktree attestation.
- A durable worker supervisor/restart test. Codespaces stopping is expected to terminate processes; it cannot be claimed always-on.
- External GitHub port routing and OAuth validation, a custom plugin connection and a successful normal-chat MCP call.
- A paired Codex-quality task evaluation.

No result from a local fixture substitutes for an actual ChatGPT tool call. Do not claim the connection works until that call is observed.
