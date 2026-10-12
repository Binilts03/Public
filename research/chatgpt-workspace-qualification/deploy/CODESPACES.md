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

## Recover runtime import failure after successful worker isolation

On the actual Codespace, the first OAuth controller launch failed its health
check, and the diagnostic confirmed `controller_python_import: NO` while the
runtime executable and secrets existed. The original privileged installer
set `umask 077` for all files, inadvertently making the Python runtime
directories non-traversable by the distinct controller UID. An independent
Python virtualenv fixture reproduced directory mode `0700` under this umask.

**Do not rerun the privileged installer or regenerate the OAuth secrets.**
The dedicated runtime repair applies only to root-owned public-code files under
`/opt/public-chatgpt-mcp/venv`, only when the controller and worker are
stopped and the earlier root-only isolation attestation is present. It rejects
unexpected symlinks, confirms controller/worker imports and rechecks the
original Codespaces ACL and OAuth secret boundary.

```bash
cd /workspaces/Public
git pull --ff-only origin experiments/chatgpt-workspace-qualification
python3 -m py_compile research/chatgpt-workspace-qualification/deploy/codespaces-repair-runtime.py
sudo python3 research/chatgpt-workspace-qualification/deploy/codespaces-repair-runtime.py
```

Require `RUNTIME_PERMISSIONS_REPAIRED_PASS` and
`NO_SECRETS_CHANGED_NO_PROCESS_STARTED_NO_PORT_EXPOSED`.
Only then retry `codespaces-start-controller.sh "$CODESPACE_NAME"`.
The launcher now tests controller-user runtime imports *before* starting and
preserves the original private crash log. A failed import is not evidence
that the server is externally available.

## Live localhost OAuth → worker execution qualification

After `LOCAL_CONTROLLER_GATE_PASS`, leave port 8765 **Private** and run:

```bash
cd /workspaces/Public
git pull --ff-only origin experiments/chatgpt-workspace-qualification
/opt/public-chatgpt-mcp/venv/bin/python -m py_compile \
  research/chatgpt-workspace-qualification/deploy/codespaces-enroll-verify-worker.py
sudo /opt/public-chatgpt-mcp/venv/bin/python \
  research/chatgpt-workspace-qualification/deploy/codespaces-enroll-verify-worker.py
```

The program validates the previously qualified Linux identities, root-owned
runtime and Public-only disabled-push worktree; reads OAuth credentials only
inside the root process; obtains an expiring locally bound OAuth token using
S256 PKCE; rejects missing/invalid bearer tokens and OAuth code replay;
proves controller shell execution is disabled; requests an invite; passes
the single-use worker invite via a pipe to `chatgpt-worker` (never an argument);
and runs a **read-only shell command** on the isolated Public worker. It
verifies output markers for worker identity, git root, disabled push remote,
controller-credential inaccessibility, original-workspace ACL denial and
Docker-socket denial.

The program does **not** publish a port, push Git commits, change the original
worktree, or expose credentials in its output. On verified success it
intentionally leaves the worker running as `chatgpt-worker` for the next
ordinary-ChatGPT plugin connection gate. This is a temporary Codespaces
qualification, not a supervised always-on worker. A crashed/suspended
Codespace requires lifecycle revalidation.

Success requires `LOCAL_OAUTH_PKCE_PASS`,
`LOCAL_MCP_CONTROL_PLANE_PASS`,
`WORKER_ENROLLMENT_AND_REMOTE_SHELL_PASS`,
and `PORT_VISIBILITY_UNCHANGED`.

**Do not rerun this enrollment script** after it has registered the worker.
If an intermediate step fails, worker identity or authorization state might
have been persisted. Preserve it and diagnose separately; never wipe
`/srv/chatgpt-worker/state` or regenerate the controller OAuth secret to
make a failing test pass.

## Interpreting a worker-access failure under /workspaces

A real Codespaces run passed `LOCAL_CONTROLLER_GATE_PASS` but the live
enrollment script stopped at `BLOCKED: worker can write another workspace`
before obtaining an OAuth token or inviting a worker.

This is a host-access denial, not an indication of missing Python
dependencies. **Do not rerun enrollment or modify ACLs on other repositories.**
Use the read-only inventory below, which probes `/workspaces` and immediate
entries only; it reads no Git files, no credentials and no directory contents:

```bash
cd /workspaces/Public
git pull --ff-only origin experiments/chatgpt-workspace-qualification
python3 -m py_compile research/chatgpt-workspace-qualification/deploy/codespaces-diagnose-workspaces.py
sudo python3 research/chatgpt-workspace-qualification/deploy/codespaces-diagnose-workspaces.py
```

Interpret `BLOCKER_ROOT` as a writable **parent** directory, and
`BLOCKER_SIBLING` as an independently writable immediate child (which
could be a symlink). Record only the paths/metadata shown, not the contents
of any sibling repository. The worker must not be permitted to write
unrelated checkouts; never apply a mass `chmod` or `setfacl` over
`/workspaces` or other repos. There is a targeted remediation for this host layout: deny only
`chatgpt-worker` traversal on the **/workspaces parent**, not on any
sibling or child checkout. Because the allowed worker checkout is entirely
under `/srv/chatgpt-worker`, this does not remove needed access. The
script first validates the existing Public-only installation, requires the
worker to be stopped, saves a root-only snapshot of the current parent ACL,
and uses `setfacl -n` (preserve the existing ACL mask). It then confirms
that the Codespace owner can still access Public and that the worker cannot
read or write sibling workspace paths.

```bash
cd /workspaces/Public
git pull --ff-only origin experiments/chatgpt-workspace-qualification
bash -n research/chatgpt-workspace-qualification/deploy/codespaces-deny-worker-workspaces.sh
sudo bash research/chatgpt-workspace-qualification/deploy/codespaces-deny-worker-workspaces.sh
```

**Only after** `PARENT_WORKSPACE_ISOLATION_PASS` may the guarded
`codespaces-enroll-verify-worker.py` be run again. The previous enrollment
attempt failed in `host_gate()` before it created an OAuth client, invite,
worker process, or identity. If a *future* enrollment attempt reaches OAuth
or enrollment and fails, do not automatically retry: enrollment state might
have been persisted. If the parent ACL change fails or owner access changes,
stop and diagnose the existing ACL; do not chmod or change other repositories.

The enrollment preflight now also rejects a writable `/workspaces` parent:
protecting each existing checkout does not prevent a worker from creating
new entries within a writable parent.

## Interrupted live worker enrollment: preserve state before recovery

Observed in the real Codespace after `PARENT_WORKSPACE_ISOLATION_PASS`
and `LOCAL_CONTROLLER_GATE_PASS`:
`LOCAL_OAUTH_PKCE_PASS` and `LOCAL_MCP_CONTROL_PLANE_PASS`, then
`BLOCKED: private MCP OAuth/worker verification failed`.

This means a one-time invitation was created and the worker launch was
attempted; it does **not** prove whether registration completed. The
qualification script intentionally terminates the process it spawned on
failure, but the worker may have persisted an identity and the controller
may have persisted a registration. **Do not rerun enrollment** until this
state has been inspected. Do not print raw logs or worker state (they may
contain bearer tokens).

```bash
cd /workspaces/Public
git pull --ff-only origin experiments/chatgpt-workspace-qualification
python3 -m py_compile research/chatgpt-workspace-qualification/deploy/codespaces-diagnose-worker-enrollment.py
sudo /opt/public-chatgpt-mcp/venv/bin/python \
  research/chatgpt-workspace-qualification/deploy/codespaces-diagnose-worker-enrollment.py
```

The read-only diagnostic reports only whether `identity.json`,
`config.json`, controller registration state and the worker's private log
exist, their ownership/mode, whether a worker remains running, and fixed
log-error categories. It does not read or print secrets. Share this sanitized
output to determine the recovery plan. A stale existing invitation is not
reused blindly.

Two pre-existing test-script issues were corrected for *future* use:
`subprocess.Popen` now explicitly starts inside the authorized
`/srv/chatgpt-worker/worktrees/Public` directory instead of inheriting
the protected `/workspaces/Public` cwd, and the remote shell command no
longer references the Docker socket, which is blocked by the upstream
`command_denylist`. The socket's inaccessibility remains verified in the
privileged preflight under the worker UID.

## Stage 3 real worker execution and independently requalified stdout

Live Codespaces evidence (2026-10-12): authenticated controller and remote
worker passed, leaving the enrolled worker running. The controller reports
"worker_online": true and "remote_read_only_command": "PASS"; original workspace
and controller credentials remained inaccessible to the worker, including
Docker socket denial independently checked in privileged preflight.

**Proof caveat fixed before external ingress:** the original MCP remote
verification searched JSON-serialized results for marker text. Since the
upstream shell response includes the executed `command` as well as `stdout`,
the marker search could be satisfied by the echoed command even if some
remote denial checks failed. A new verifier now demands the exact ordered
`stdout` lines, checks exit code, timeout and truncation, and runs the
negative permissions checks as standalone tests under `set -eu`.

The enrolled worker MUST NOT be invited again. The requalification below
reads the existing worker and controller identities, compares their private
access credentials in memory, reuses the running worker, and verifies actual
remote shell output. It registers one new short-lived OAuth *test client*
for localhost authentication, but does not change any worker identity,
create a worker invitation, launch a second process, or expose any port:

```bash
cd /workspaces/Public
git pull --ff-only origin experiments/chatgpt-workspace-qualification
sudo /opt/public-chatgpt-mcp/venv/bin/python \
  research/chatgpt-workspace-qualification/deploy/codespaces-reverify-enrolled-worker.py
```

Expected exact final markers:
`ENROLLED_WORKER_IDENTITY_BOUND_PASS`,
`EXISTING_WORKER_OAUTH_PKCE_PASS`, and
`EXISTING_WORKER_REMOTE_STDOUT_AND_DENIAL_PASS`.
If the process is no longer running or any check fails, do not reenroll,
reset the worker's identity, or expose the Codespaces port. Preserve the
private logs/state and diagnose.

**External ChatGPT app/plugin transport is a separate, still-unqualified
gate.** A private Codespaces forwarded port enforces GitHub authentication,
which ChatGPT's OAuth client cannot simply bypass. Public port visibility
would remove that GitHub layer and expose the MCP/OAuth server to unauthenticated
Internet traffic. Any external ingress must be explicitly approved and
separately threat-modelled before use. Codespace shutdown terminates its
running worker because this stage deliberately does not install a persistent
supervisor. A successful localhost test is NOT production readiness.

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
