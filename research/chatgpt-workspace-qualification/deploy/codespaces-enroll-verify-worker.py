#!/usr/bin/env python3
"""Qualify a live Codespaces OAuth controller and Public-only remote worker.

Intentionally affects only the existing isolated Codespace deployment:
- Reads the controller's private env as root without logging credential values.
- Registers one test OAuth client and obtains a short-lived bearer token.
- Creates exactly one remote worker invitation and passes it through a pipe.
- Starts worker ONLY as chatgpt-worker, with a sanitized environment.
- Proves the controller refuses local shell and the remote Public worktree runs.
- Keeps the worker alive on PASS for the separate ChatGPT connection gate.
No Git writes/push, no external/public HTTP requests or port visibility changes.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import shlex
import signal
import socket
import stat
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

CTRL_USER = "chatgpt-controller"
WORKER_USER = "chatgpt-worker"
ORIGINAL = Path("/workspaces/Public")
CTRL_ROOT = Path("/srv/chatgpt-controller")
WORKER_ROOT = Path("/srv/chatgpt-worker")
WORKTREE = WORKER_ROOT / "worktrees/Public"
VENV = Path("/opt/public-chatgpt-mcp/venv")
# Always invoke runuser by absolute path: the worker launcher intentionally
# removes /usr/sbin from PATH and an unqualified name cannot be executed.
RUNUSER = Path("/usr/sbin/runuser")
QUALIFIED = Path("/opt/public-chatgpt-mcp/codespaces-isolation-qualified")
CONTROLLER_CONFIG = CTRL_ROOT / "controller.env"
WORKER_CONFIG = WORKER_ROOT / "worker.env"
WORKER_LOG = WORKER_ROOT / "logs/worker.log"
HOST = "http://127.0.0.1:8765"
NAME = "public-worker"
PINNED_UPSTREAM = "dec01b9f50f966097ddfc84d357d12a52f238935"
EXPECTED_REPO = "https://github.com/Binilts03/Public.git"
EXPECTED_PUSH = "no-push://disabled"

# Controlled, non-secret diagnostics. Never expose arbitrary exception text,
# invitations, bearer tokens, raw worker logs, or registry file contents.
FAILURE_STAGE = ["preflight"]

class GateFailure(Exception):
    pass

def require(condition: bool, reason: str) -> None:
    if not condition:
        raise GateFailure(reason)

def as_user(user: str, argv: list[str]) -> bool:
    return subprocess.run(
        [str(RUNUSER), "-u", user, "--", *argv],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12,
        check=False,
    ).returncode == 0

def read_controller_credentials() -> dict[str, str]:
    # Not a shell: no eval, sourcing, expansion or printing of environment data.
    permitted = {
        "LOCAL_SHELL_MCP_PUBLIC_BASE_URL",
        "LOCAL_SHELL_MCP_OAUTH_ADMIN_PIN",
        "LOCAL_SHELL_MCP_OAUTH_JWT_SECRET",
        "LOCAL_SHELL_MCP_DISABLE_LOCAL",
        "LOCAL_SHELL_MCP_REMOTE_ENABLED",
        "LOCAL_SHELL_MCP_AUTH_BYPASS_LOCALHOST",
        "LOCAL_SHELL_MCP_AUTH_MODE",
    }
    data: dict[str, str] = {}
    for line in CONTROLLER_CONFIG.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key in permitted:
            require(key not in data, "duplicate controller configuration field")
            data[key] = value
    require(data.get("LOCAL_SHELL_MCP_DISABLE_LOCAL") == "true",
            "local shell execution must be disabled")
    require(data.get("LOCAL_SHELL_MCP_REMOTE_ENABLED") == "true", "remote mode not enabled")
    require(data.get("LOCAL_SHELL_MCP_AUTH_BYPASS_LOCALHOST") == "false",
            "localhost OAuth bypass not disabled")
    require(data.get("LOCAL_SHELL_MCP_AUTH_MODE") == "oauth", "OAuth must be enforced")
    require(len(data.get("LOCAL_SHELL_MCP_OAUTH_ADMIN_PIN", "")) >= 16,
            "admin PIN absent or too weak")
    require(len(data.get("LOCAL_SHELL_MCP_OAUTH_JWT_SECRET", "")) >= 48,
            "JWT signing secret absent or too weak")
    public = data.get("LOCAL_SHELL_MCP_PUBLIC_BASE_URL", "")
    require(public.startswith("https://") and
            public.endswith("-8765.app.github.dev") and
            "REPLACE" not in public and
            urlsplit(public).path in {"", "/"},
            "controller external OAuth origin invalid")
    return data

def require_clean_worker_registration() -> None:
    """Read controller registry metadata before creating another worker invitation.

    A missing worker-side identity alone does not prove that the controller
    has no persisted registration. Print no tokens or invitation codes.
    """
    registry = CTRL_ROOT / "state/remote-workers.json"
    require(registry.is_file() and not registry.is_symlink(),
            "worker registry absent/untrusted; run read-only diagnostic")
    info = registry.stat()
    require(info.st_uid == pwd.getpwnam(CTRL_USER).pw_uid
            and stat.S_IMODE(info.st_mode) == 0o600,
            "worker registry is not controller-owned private state")
    try:
        payload = json.loads(registry.read_text(encoding="utf-8"))
        require(isinstance(payload, dict) and payload.get("version") == 1,
                "worker registry format invalid")
        workers, invites = payload.get("workers"), payload.get("invites")
        require(isinstance(workers, list) and isinstance(invites, list),
                "worker registry fields invalid")
        require(all(isinstance(row, dict) for row in workers + invites),
                "worker registry records invalid")
        require(not workers, "controller already has a worker registration; do not reenroll")
        now = time.time()
        require(not any(
            float(row.get("expires_at", 0)) > now and not row.get("used", False)
            for row in invites
        ), "previous invitation remains active; do not create a second")
    except (ValueError, TypeError, OverflowError):
        raise GateFailure("invalid worker registry; no new invitation created") from None
    for name in ("identity.json", "identity.json.tmp", "config.json", "config.json.tmp"):
        require(not (WORKER_ROOT / "state" / name).exists(),
                "saved worker identity/config present; diagnose before enrollment")


def host_gate():
    require(os.geteuid() == 0 and os.environ.get("SUDO_USER") == "codespace",
            "run as sudo Python from the Codespaces owner account")
    require(len(sys.argv) == 1, "unexpected arguments")
    require(RUNUSER.is_file() and os.access(RUNUSER, os.X_OK)
            and RUNUSER.stat().st_uid == 0,
            "root-owned /usr/sbin/runuser missing or not executable")
    require(QUALIFIED.is_file() and
            QUALIFIED.stat().st_uid == 0 and
            stat.S_IMODE(QUALIFIED.stat().st_mode) == 0o600,
            "isolation attestation missing or not private")
    require(WORKTREE.is_dir() and not WORKTREE.is_symlink(),
            "isolated Public worktree not present")
    require(CONTROLLER_CONFIG.is_file() and
            CONTROLLER_CONFIG.stat().st_uid == pwd.getpwnam(CTRL_USER).pw_uid and
            stat.S_IMODE(CONTROLLER_CONFIG.stat().st_mode) == 0o600,
            "controller private OAuth config incorrectly owned")
    require(WORKER_CONFIG.is_file() and
            WORKER_CONFIG.stat().st_uid == pwd.getpwnam(WORKER_USER).pw_uid and
            stat.S_IMODE(WORKER_CONFIG.stat().st_mode) == 0o600,
            "worker private configuration incorrectly owned")
    require(pwd.getpwnam(WORKER_USER).pw_uid != pwd.getpwnam(CTRL_USER).pw_uid,
            "worker and controller share an identity")
    for group in ("docker", "sudo", "ssh"):
        require(group not in subprocess.check_output(
            ["id", "-nG", WORKER_USER], text=True).split(),
            "worker has unexpected elevated group")
    for path in ("/var/run/docker.sock", "/run/docker.sock"):
        if os.path.exists(path):
            require(not as_user(WORKER_USER, ["test", "-r", path]) and
                    not as_user(WORKER_USER, ["test", "-w", path]),
                    "worker can use privileged Docker socket")
    for path in (str(ORIGINAL), "/srv/chatgpt-controller/controller.env"):
        require(not as_user(WORKER_USER, ["test", "-w", path]),
                "worker can write protected path")
    require(not as_user(WORKER_USER, ["test", "-x", str(ORIGINAL)]),
            "worker can traverse original Codespace checkout")
    require(not as_user(WORKER_USER, ["test", "-r", str(CONTROLLER_CONFIG)]),
            "worker can read controller OAuth credential file")
    require(not as_user(CTRL_USER, ["test", "-r", str(WORKER_CONFIG)]),
            "controller can read worker configuration")
    # A worker with write access to /workspaces can create new sibling paths
    # even if every existing sibling is separately protected.
    require(not as_user(WORKER_USER, ["test", "-w", "/workspaces"]),
            "worker can write /workspaces root; run codespaces-diagnose-workspaces.py")
    for other in Path("/workspaces").iterdir():
        if other.is_dir() and other != ORIGINAL:
            require(not as_user(WORKER_USER, ["test", "-w", str(other)]),
                    "worker can write another workspace; run codespaces-diagnose-workspaces.py")
    source = Path("/opt/public-chatgpt-mcp/source")
    require(subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() ==
        PINNED_UPSTREAM, "root-owned MCP source pin mismatch")
    git_base = [str(RUNUSER), "-u", WORKER_USER, "--", "env", "-i",
                "HOME=/srv/chatgpt-worker/home", "PATH=/usr/bin:/bin",
                "GIT_TERMINAL_PROMPT=0", "git", "-C",
                str(WORKER_ROOT / "git/Public")]
    def git(*args):
        return subprocess.check_output(
            [*git_base, *args], stderr=subprocess.DEVNULL, timeout=15, text=True
        ).strip()
    require(git("remote", "get-url", "origin") == EXPECTED_REPO,
            "worker fetch remote differs from allowlisted Public")
    require(git("remote", "get-url", "--push", "origin") == EXPECTED_PUSH,
            "worker Git push remote not disabled")
    require(git("status", "--porcelain") == "", "worker Git worktree is dirty")
    require(as_user(CTRL_USER, [str(VENV / "bin/python"), "-c",
                                "import local_shell_mcp.main"]),
            "controller runtime import failed")
    require(as_user(WORKER_USER, [str(VENV / "bin/python"), "-c",
                                  "import local_shell_mcp.remote_worker"]),
            "worker runtime import failed")
    require(as_user(CTRL_USER, ["test", "-x", str(CTRL_ROOT / "state")]),
            "controller cannot access state")
    # Start only if current controller exists and loopback is accepting traffic.
    require(subprocess.run(["pgrep", "-u", CTRL_USER, "-f",
                             "nondumpable_mcp_entrypoint.py"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            check=False).returncode == 0,
            "controller not running")
    require(subprocess.run(["pgrep", "-u", WORKER_USER, "-f",
                             "local_shell_mcp.remote_worker"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            check=False).returncode != 0,
            "worker already running; do not duplicate or overwrite enrollment")
    require_clean_worker_registration()
    with socket.create_connection(("127.0.0.1", 8765), timeout=3):
        pass

def local_oauth(public_base: str, pin: str, secret: str) -> str:
    with httpx.Client(base_url=HOST, follow_redirects=False, timeout=10) as client:
        meta = client.get("/.well-known/oauth-authorization-server")
        require(meta.status_code == 200, "OAuth discovery returned non-200")
        md = meta.json()
        require(md.get("issuer") == public_base, "OAuth issuer differs from intended HTTPS origin")
        require("S256" in md.get("code_challenge_methods_supported", []),
                "OAuth provider is missing PKCE S256")
        resource = client.get("/.well-known/oauth-protected-resource")
        require(resource.status_code == 200 and
                resource.json().get("resource") == public_base,
                "OAuth protected-resource metadata is inconsistent")
        init = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "qualify-unauthenticated", "version": "1"}},
        }
        headers = {"Accept": "application/json, text/event-stream",
                   "Content-Type": "application/json"}
        for auth_header in ({}, {"Authorization": "Bearer definitely-not-valid"}):
            negative = client.post("/mcp", headers={**headers, **auth_header}, json=init)
            require(negative.status_code == 401,
                    "unauthenticated/invalid bearer request was not rejected")
        redirect = "https://client.example.invalid/callback"
        registration = client.post("/oauth/register", json={
            "client_name": "public-codespaces-local-qualification",
            "redirect_uris": [redirect],
        })
        require(registration.status_code in (200, 201),
                "OAuth dynamic client registration failed")
        client_id = registration.json()["client_id"]
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip("=")
        state = secrets.token_urlsafe(18)
        params = {
            "response_type": "code", "client_id": client_id,
            "redirect_uri": redirect, "code_challenge": challenge,
            "code_challenge_method": "S256", "state": state,
            "resource": public_base,
        }
        consent = client.get("/oauth/authorize", params=params)
        require(consent.status_code == 200, "OAuth consent page unavailable")
        approval = client.post("/oauth/authorize", data={**params, "pin": pin})
        require(approval.status_code == 302, "OAuth PIN authorization failed")
        parsed = parse_qs(urlsplit(approval.headers["location"]).query)
        require(parsed.get("state") == [state] and parsed.get("iss") == [public_base],
                "OAuth redirect state or issuer mismatch")
        code = parsed["code"][0]
        token_resp = client.post("/oauth/token", data={
            "grant_type": "authorization_code", "client_id": client_id,
            "redirect_uri": redirect, "code": code, "code_verifier": verifier,
            "resource": public_base,
        })
        require(token_resp.status_code == 200, "OAuth PKCE code exchange failed")
        payload = token_resp.json()
        require(payload.get("token_type", "").lower() == "bearer",
                "OAuth token type mismatch")
        token = payload["access_token"]
        claims = jwt.decode(token, secret, algorithms=["HS256"],
                            audience=public_base, issuer=public_base)
        require(claims["client_id"] == client_id, "OAuth client binding failed")
        require(0 < claims["exp"] - claims["iat"] <= 3600,
                "OAuth bearer lifetime unexpectedly long")
        replay = client.post("/oauth/token", data={
            "grant_type": "authorization_code", "client_id": client_id,
            "redirect_uri": redirect, "code": code, "code_verifier": verifier,
            "resource": public_base,
        })
        require(replay.status_code == 400, "OAuth code replay unexpectedly accepted")
        return token

async def mcp_call(session: ClientSession, tool_name: str, arguments: dict) -> dict:
    result = await session.call_tool(tool_name, arguments)
    payload = result.structuredContent or {}
    require(not result.isError and payload.get("ok") is True,
            f"{tool_name} request rejected")
    return payload.get("data") or {}

async def mcp_test(token: str) -> tuple[dict, str]:
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token},
                                  timeout=httpx.Timeout(20, read=80)) as http:
        async with streamable_http_client(HOST + "/mcp", http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                tools = {x.name for x in (await session.list_tools()).tools}
                require({"remote_manage", "run_shell"} <= tools,
                        "necessary remote MCP tools not discoverable")
                # Even authenticated, controller MUST refuse local shell.
                local = await session.call_tool("run_shell",
                    {"command": "echo DISALLOWED_LOCAL_EXECUTION"})
                require(local.isError or not (local.structuredContent or {}).get("ok"),
                        "controller executed a command locally")
                before = await mcp_call(session, "remote_manage", {"action": "list"})
                machines = before.get("machines", [])
                require(not any(x.get("name") == NAME for x in machines),
                        "Public worker already registered; fail rather than duplicate")
                invite_data = await mcp_call(session, "remote_manage", {
                    "action": "invite", "name": NAME,
                    "workdir": str(WORKTREE), "ttl_s": 180,
                })
                code = invite_data.get("code", "")
                require(code.startswith("lsmcp_inv_"), "expected one-time invite missing")
                return {"tool_count": len(tools), "local_shell_denied": True}, code

def spawn_worker(invite: str) -> subprocess.Popen:
    worker = pwd.getpwnam(WORKER_USER)
    kwargs = {
        "HOME": str(WORKER_ROOT / "home"),
        "XDG_CONFIG_HOME": str(WORKER_ROOT / "home/.config"),
        "PATH": str(VENV / "bin") + ":/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "LOCAL_SHELL_MCP_WORKSPACE_ROOT": str(WORKTREE),
        "LOCAL_SHELL_MCP_WORKER_STATE_DIR": str(WORKER_ROOT / "state"),
        "LOCAL_SHELL_MCP_STATE_DIR": str(WORKER_ROOT / "state"),
        "LOCAL_SHELL_MCP_AGENT_CONFIG_DIR": str(WORKER_ROOT / "skills"),
        "LOCAL_SHELL_MCP_REMOTE_ENABLED": "false",
        "LOCAL_SHELL_MCP_AUTH_MODE": "none",
        "LOCAL_SHELL_MCP_ALLOW_FULL_CONTAINER": "false",
        "LOCAL_SHELL_MCP_UI_ENABLED": "false",
        "LOCAL_SHELL_MCP_LIVE_WORKSPACE_ENABLED": "false",
    }
    argv = [str(RUNUSER), "-u", WORKER_USER, "--", "env", "-i",
            *[f"{k}={v}" for k,v in kwargs.items()],
            str(VENV / "bin/python"), "-m", "local_shell_mcp.remote_worker",
            "connect", "--server", HOST, "--invite-stdin",
            "--name", NAME, "--workdir", str(WORKTREE)]
    logfd = os.open(WORKER_LOG,
                    os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    os.fchown(logfd, worker.pw_uid, worker.pw_gid)
    os.fchmod(logfd, 0o600)
    try:
        # Never inherit /workspaces/Public as cwd: the worker is
        # deliberately denied traversal of that checkout and /workspaces.
        p = subprocess.Popen(argv, stdin=subprocess.PIPE,
                             stdout=logfd, stderr=subprocess.STDOUT,
                             cwd=str(WORKTREE),
                             start_new_session=True, env={
                                 "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                             })
    finally:
        os.close(logfd)
    require(p.stdin is not None, "worker invitation pipe unavailable")
    try:
        p.stdin.write((invite + "\n").encode())
        p.stdin.close()
    except BaseException:
        # Failure writing invitation must not strand a privileged launcher.
        stop_our_worker(p)
        raise
    return p

def verify_remote_stdout(result: dict) -> None:
    """Verify ACTUAL remote command stdout, not echoed command arguments.

    Upstream CommandResult includes a 'command' field, so searching a dumped
    payload for an echo sentinel produces a false-positive proof. Every
    asserted line must be present in the independently returned stdout.
    """
    require(isinstance(result, dict), "remote shell result has invalid shape")
    require(result.get("exit_code") == 0, "remote shell command failed")
    require(result.get("timed_out") is False, "remote shell timed out")
    require(result.get("truncated") is False, "remote shell output was truncated")
    require(isinstance(result.get("stdout"), str),
            "remote shell stdout is absent or invalid")
    expected = [
        WORKER_USER,
        str(WORKTREE),
        str(WORKTREE),
        EXPECTED_PUSH,
        "CTRL_SECRETS_HIDDEN",
        "ORIGINAL_REPO_PROTECTED",
        "ORIGINAL_REPO_TRAVERSAL_DENIED",
    ]
    actual = result["stdout"].splitlines()
    require(actual == expected,
            "remote stdout did not exactly match independently required identity, workspace and denial checks")


async def verify_remote(token: str, process: subprocess.Popen | None) -> dict:
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token},
                                  timeout=httpx.Timeout(20, read=90)) as http:
        async with streamable_http_client(HOST + "/mcp", http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if process is not None:
                        require(process.poll() is None, "worker process exited during enrollment")
                    inventory = await mcp_call(session, "remote_manage", {"action": "list"})
                    entries = inventory.get("machines", [])
                    if any(x.get("name") == NAME and x.get("status") == "online"
                           for x in entries):
                        break
                    await asyncio.sleep(.8)
                else:
                    raise GateFailure("worker did not appear online within verification window")
                check = (
                    "set -eu; "
                    "id -un; "
                    "pwd; "
                    "git rev-parse --show-toplevel; "
                    "git remote get-url --push origin; "
                    "test ! -r /srv/chatgpt-controller/controller.env; "
                    "printf 'CTRL_SECRETS_HIDDEN\n'; "
                    "test ! -w /workspaces/Public; "
                    "printf 'ORIGINAL_REPO_PROTECTED\n'; "
                    "test ! -x /workspaces/Public; "
                    "printf 'ORIGINAL_REPO_TRAVERSAL_DENIED\n'"
                )
                result = await mcp_call(session, "run_shell", {
                    "command": check, "machine": NAME, "cwd": ".", "timeout_s": 25,
                })
                verify_remote_stdout(result)
                return {
                    "worker_online": True,
                    "remote_read_only_command": "PASS",
                    "controller_local_execution_refused": True,
                    "worker_secret_denial": "PASS",
                    "worker_original_repo_denial": "PASS",
                    "worker_docker_socket_denial_preflight": "PASS",
                }

def stop_our_worker(p: subprocess.Popen) -> None:
    if p.poll() is None:
        try:
            os.killpg(p.pid, signal.SIGTERM)
            p.wait(timeout=7)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

def main() -> None:
    FAILURE_STAGE[0] = "host_preflight"
    host_gate()
    FAILURE_STAGE[0] = "oauth_exchange"
    config = read_controller_credentials()
    token = local_oauth(
        config["LOCAL_SHELL_MCP_PUBLIC_BASE_URL"],
        config["LOCAL_SHELL_MCP_OAUTH_ADMIN_PIN"],
        config["LOCAL_SHELL_MCP_OAUTH_JWT_SECRET"],
    )
    print("LOCAL_OAUTH_PKCE_PASS: discovery, JWT issuer/audience, 401 negatives and replay rejection")
    FAILURE_STAGE[0] = "mcp_control_plane"
    summary, invite = asyncio.run(mcp_test(token))
    print("LOCAL_MCP_CONTROL_PLANE_PASS: tools discovered, local shell denied, one-time invite created")
    FAILURE_STAGE[0] = "worker_spawn"
    worker = spawn_worker(invite)
    FAILURE_STAGE[0] = "remote_verification"
    try:
        result = asyncio.run(verify_remote(token, worker))
        require(worker.poll() is None, "worker disappeared after verification")
    except BaseException:
        stop_our_worker(worker)
        raise
    FAILURE_STAGE[0] = "success"
    print("WORKER_ENROLLMENT_AND_REMOTE_SHELL_PASS:", json.dumps(result, sort_keys=True))
    print("WORKER_PROCESS_PID:", worker.pid)
    print("WORKER_LEFT_RUNNING_FOR_CONNECTION_GATE: yes (not supervised across Codespace shutdown)")
    print("PORT_VISIBILITY_UNCHANGED: no public ingress configured")
    print("NO_GIT_WRITES_NO_SECRETS_PRINTED")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        # Fixed stage and Python exception TYPE only; not exception messages,
        # network responses or any invite/worker credential content.
        cls = type(exc).__name__
        error = getattr(exc, "errno", None)
        errno_part = (" errno=" + str(error)) if isinstance(error, int) else ""
        print("BLOCKED: stage=" + FAILURE_STAGE[0] +
              " class=" + cls + errno_part +
              " (no credentials/logs disclosed)", file=sys.stderr)
        raise SystemExit(2)
