# Staged Public coding workspace — operator runbook (NOT deployment approval)

**Scope:** ONLY Binilts03/Public and the isolated qualification branch. This runbook is for a dedicated disposable Linux VM. Do not install it on a machine containing other valuable repositories.

## Evidence for this package

- [Controller/worker remote isolation PASS](https://github.com/Binilts03/Public/actions/runs/38156038335) — different Linux UIDs, controller local execution refused, real remote shell, controller OAuth process/state unreadable.
- [Single-user OAuth credential exposure FAIL](https://github.com/Binilts03/Public/actions/runs/38154762634) — never run the default controller as the shell worker.
- [Two-user staged installer PASS](https://github.com/Binilts03/Public/actions/runs/38156645669) — ephemeral Ubuntu 24.04; exact backend pinned, Public-only worktree, both services disabled.

## Architecture

1. `chatgpt-coder.service`: OAuth/controller-only server, bound to `127.0.0.1:8765`, user `chatgpt-controller`, no local shell/filesystem access, credentials/state private to controller.
2. `chatgpt-worker.service`: remote polling coding worker, user `chatgpt-worker`, working only in `/srv/chatgpt-worker/worktrees/Public` with no Git push credentials. It stores its **own worker enrollment token**, not the controller OAuth secrets.
3. Public HTTPS ingress: optionally Tailscale Funnel on a separate managed process. HTTPS alone does not authenticate; MCP OAuth is mandatory.
4. ChatGPT private plugin: client for the OAuth-protected Streamable HTTP `/mcp` endpoint, if the user's account permits custom write-capable plugin tools.

## Installation — staged, never auto-activated

Use a dedicated, newly provisioned Ubuntu 24.04 instance with systemd and Python 3.11+; install prerequisites such as git, python3-venv, ca-certificates and openssl. Obtain this deployment folder from the **qualification branch** of `Binilts03/Public`; inspect files before executing.

Run `sudo bash install-staged.sh` from the checked-out deployment directory. The script checks exact upstream SHA `dec01b9f50f966097ddfc84d357d12a52f238935`, installs the Python backend, creates two users, clones only Public, and creates both systemd units with disabled status. It does **not** start anything, issue remote worker invites, publish a URL, or connect to ChatGPT.

Manual preflight checks: `sudo systemctl is-enabled chatgpt-coder chatgpt-worker` should report disabled; `sudo systemctl is-active chatgpt-coder chatgpt-worker` should not report active; check `sudo stat -c '%U:%a' /srv/chatgpt-controller/state /srv/chatgpt-worker/state /etc/chatgpt-coder/controller.env` and verify owner/0700/0600 as applicable. Never output JWT/PIN values into chat or CI logs.

## Activation gate — blocked until host operator has checked these points

- Confirm the VM has no accessible sensitive repositories, SSH keys, provider tokens or Docker socket, and that controller/worker cannot read one another's protected directories. The service units are templates, not production security certification.
- Replace `LOCAL_SHELL_MCP_PUBLIC_BASE_URL=https://REPLACE-WITH-AUTHORIZED-HOST.invalid` in the **root-only controller environment file** with the actual externally resolvable HTTPS origin. Validate TLS, reverse proxy forwarded Host/origin behaviour, OAuth discovery and callback redirects before enabling any shell access.
- Start **only the controller** initially and check that local `run_shell` is refused. `LOCAL_SHELL_MCP_DISABLE_LOCAL=true` and `LOCAL_SHELL_MCP_REMOTE_ENABLED=true` must remain enforced.
- Create a one-time `remote_manage(action="invite", name="public-worker", workdir="/srv/chatgpt-worker/worktrees/Public")` via a properly authenticated MCP client. Never embed the invite in this public repo, workflow logs or printed installation output.
- Enroll the worker as its own system account using upstream `local-shell-mcp worker enroll --server http://127.0.0.1:8765 --invite <one-time-code> --name public-worker --workdir /srv/chatgpt-worker/worktrees/Public`, with the worker-specific HOME/state variables and without controller OAuth secrets. Only then start `chatgpt-worker.service`.
- Verify `remote_manage(action="list")` shows only the expected worker; verify `run_shell(machine="public-worker")` works on an inconsequential fixture, while `run_shell` without machine is refused. Repeat controller-secret state/file read tests from that worker.
- Restart both **systemd** services and reconcile a live job. This remains untested: prior job tests terminated the MCP OS process without invoking systemd's `KillMode=control-group` behavior.
- Connect the private plugin in an ordinary ChatGPT conversation, confirm authorization and that source/writes are limited to Public, then run a real RED-GREEN repair in an isolated worktree. No destructive Git action without approval.

## Quality gate

Do not claim Codex-parity after the plugin connects. Version-pin the user's authorized skill roots and project instructions **privately**. Never copy private/user-custom skills or credentials into the public repository. Run paired tasks against a frozen Public SHA, including true skill activation, failing test reproduction, repair, broad regression, independent review evidence, continuation and explicit blocked states.

## Release state

**NOT PRODUCTION READY.** The persistent host, external HTTPS/OAuth flow, custom normal-chat plugin, real skills, systemd process lifecycle and paired Codex-quality outcomes have not been demonstrated. No PR/merge/push-to-main authorized.
