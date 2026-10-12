# Secure MCP Tunnel — Public Codespaces deployment

**Scope:** existing `Binilts03/Public` qualification Codespace only. Does not replace or restart the already-enrolled `public-worker`, alter other repositories, expose Codespaces port 8765, call a model API, or configure paid inference.

This package uses the documented `openai/tunnel-client` `sample_mcp_with_dcr` schema (see [configuration reference](https://github.com/openai/tunnel-client/blob/master/docs/configuration.md)) and **existing** tunnel ID `tunnel_6acd09e0298481919ac84778501b0aef`.

## Pinned dependency and explicit trust boundary

- Release: [`openai/tunnel-client` v0.0.15](https://github.com/openai/tunnel-client/releases/tag/v0.0.15), Linux AMD64
- Asset: `tunnel-client-v0.0.15-linux-amd64.zip`
- SHA-256: `8c836dc5d68d68b663d9a5c5b28ff9fa780d9f7a3fffb1c306880b8f32fab5f1`, verified against the official release's asset digest
- Binary and bundled `cloudflared`: `/opt/public-chatgpt-tunnel/`
- Non-secret installed profile: `/opt/public-chatgpt-tunnel/profile.yaml`
- Operator and daemon UID: separate `chatgpt-tunnel` system account, denied traversal of the `/workspaces` parent (no sibling repository permissions changed)
- Secret: `/srv/chatgpt-tunnel/runtime.key`, owned by `chatgpt-tunnel`, mode `0600`; not in repository, CLI arguments, profile, GitHub Actions or output
- MCP target: `http://127.0.0.1:8765/mcp` using the existing controller; dedicated health listener `127.0.0.1:8770`
- Runtime key is passed as `CONTROL_PLANE_API_KEY` in the **child process environment only**. Never use an OpenAI Platform admin key for the long-running tunnel client.

## Guarded activation stages

Do not paste the **expected output** as terminal commands. Run from the `codespace` shell in the existing Codespace.

**1. Validate the checked-in non-secret profile** (offline, no elevated privileges):

```bash
cd /workspaces/Public
git pull --ff-only origin experiments/chatgpt-workspace-qualification
python3 research/chatgpt-workspace-qualification/deploy/tunnel/manage.py validate
```

Expected: `TUNNEL_NON_SECRET_PROFILE_VALID`.

**2. Explicitly install the pinned binary**, without starting it:

```bash
sudo /usr/bin/python3 research/chatgpt-workspace-qualification/deploy/tunnel/manage.py install
```

This downloads **only** the pinned upstream release asset, verifies its SHA-256 *before* touching host state, refuses unexpected ZIP members/symlinks, creates the separate tunnel identity and denies it access to `/workspaces`, and stages the verified binaries. It is deliberately **not an idempotent overwrite**: an existing install must be diagnosed, not silently reset.

**Controller/worker processes are not prerequisites for installing the client or provisioning its runtime key.** Codespaces can stop those processes across shutdown; this must not block a read-only download and installation. `doctor` and `run` still require a running controller and already-enrolled worker. Neither command restarts them. If either process is absent, inspect state using `codespaces-diagnose-worker-enrollment.py` before considering any recovery. Never issue another worker invitation just because a process stopped.

A previous live install attempt printed `BLOCKED: controller is not running`. It failed during preflight **before the download or system modifications**. After pulling the fix and confirming CI, repeating `install` is appropriate, provided no unrelated partial installation already exists.

Expected: `TUNNEL_PINNED_RELEASE_INSTALLED_NO_DAEMON`.

**For existing installations created with a restrictive `umask`:** The
original installer requested directory mode `0755` but did not account
for umask, so it could produce root-owned `0700` and later block the
`key` command. This is a *possible cause* of the observed refusal; do
not assume ownership or permissions without inspecting the live host.

Run the **read-only preflight**, with no secrets or service changes:

```bash
sudo /usr/bin/python3 research/chatgpt-workspace-qualification/deploy/tunnel/manage.py inspect-install
```

If it reports `TUNNEL_ROOT_DIRECTORY_MODE=0700` AND
`TUNNEL_MODE_REPAIR_ELIGIBLE_AFTER_OPERATOR_REVIEW`, use the **explicit,
one-time, guarded** directory correction:

```bash
sudo /usr/bin/python3 research/chatgpt-workspace-qualification/deploy/tunnel/manage.py repair-install-mode
```

This changes **only** the release directory from root-owned `0700` to
`0755` after checking the exact installed files, their modes/ownership,
the non-secret profile, the private runtime directory and absence of
credentials. It does **not** redownload software, change worker or
controller state, adjust other repository permissions, provision a key,
start network connections or make ports public. The command refuses
already-modified trees and is intentionally not a general-purpose chmod.
Expected result: `TUNNEL_INSTALL_MODE_REPAIRED_ROOT_0755`.

If inspection reports a different mode or `BLOCKED`, **do not use
chmod manually or reinstall**. Preserve the result and diagnose before
any state change. New installations explicitly finalize the mode
independent of inherited umask, with regression coverage.

**3. Provision a restricted runtime API key** (requires Tunnels Read + Use permissions; no key is stored in Git):

```bash
sudo /usr/bin/python3 research/chatgpt-workspace-qualification/deploy/tunnel/manage.py key
```

The prompt hides input and writes the key privately. A pre-existing key causes a refusal; this command does not rotate credentials. Create a restricted *runtime* key in OpenAI Platform, not an admin key. The key is necessary for tunnel control-plane authentication, **not for model inference**. We have not independently established the billing terms for tunnel transport: do not assume either that the traffic is free or that it requires model-usage spending. Check your Platform billing/permissions before activation.

**4. Run diagnostics** (does not reenroll worker or start the tunnel daemon):

```bash
sudo /usr/bin/python3 research/chatgpt-workspace-qualification/deploy/tunnel/manage.py doctor
```

This calls the pinned `tunnel-client doctor --profile-file /opt/public-chatgpt-tunnel/profile.yaml` under `chatgpt-tunnel` with the key injected into its environment. The upstream diagnostic may make HTTPS calls to the tunnel control plane; it does not invoke an OpenAI model.

**5. Start the tunnel in the foreground only after reviewing the doctor's report**:

```bash
sudo /usr/bin/python3 research/chatgpt-workspace-qualification/deploy/tunnel/manage.py run
```

Use a dedicated terminal. Ctrl+C stops it. No system service or auto-start is enabled. The `run` command connects outbound to OpenAI and may expose the controller's *authenticated* MCP endpoint through the tunnel to actors authorized for this tunnel. That is a security-relevant activation, not a model API request.

Inspect `http://127.0.0.1:8770/healthz`, `/readyz` and `/ui` from within Codespaces as applicable. **Do not forward the 8770 health/admin listener** or make the 8765 controller port public.

## OAuth remains a separate blocker

The controller advertises its GitHub Codespaces HTTPS URL as the OAuth issuer. The tunnel transports MCP requests and OAuth metadata but **does not automatically expose the browser-facing authorization server**. GitHub-private port authentication is not automatically a compatible OAuth proxy. Do not change the issuer, disable OAuth, bypass access controls, forward ports publicly, or tell ChatGPT a private GitHub URL is reachable until its end-to-end authentication is independently verified.

**Success criteria remain:** tunnel ready, ChatGPT account permitted to select the tunnel, browser-facing OAuth login succeeds without unsafe exposure, real MCP discovery/tool call from ordinary ChatGPT chat, and no access to any repository outside `Public`.

The existing Codespace worker is not supervised across shutdown. The tunnel is not an always-on solution.

## Failure protocol

If any command prints `BLOCKED` or the upstream doctor fails: stop; don't rerun installation, overwrite credentials or reenroll workers. Preserve protected state locally and share only credential-redacted error *categories*. Never paste the key, controller PIN, worker identity JSON, or raw process environment.

The package is part of a qualification branch and is **not production-ready** until live Codespaces installation, doctor, tunnel connection, OAuth compatibility and normal-chat tool invocation are observed.
