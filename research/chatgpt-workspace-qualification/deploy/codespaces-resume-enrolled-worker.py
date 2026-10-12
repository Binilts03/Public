#!/usr/bin/env python3
"""Strictly resume the one previously enrolled Public worker, without a new invite.

Pinned upstream run_worker normally deletes a rejected identity and may fall
back to /register. The worker-only bootstrap blocks those paths and identity
writes. Parent independently compares saved credentials to controller state
and proves actual remote output before leaving the child process running.
No Git writes, secret prints, external ingress changes, or other repositories.
"""
from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
import pwd
import signal
import stat
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path("/srv/chatgpt-worker")
WORKTREE = ROOT / "worktrees/Public"
IDENTITY = ROOT / "state/identity.json"
CONFIG = ROOT / "state/config.json"
LOG = ROOT / "logs/worker.log"
CTRL_ROOT = Path("/srv/chatgpt-controller")
REGISTRY = CTRL_ROOT / "state/remote-workers.json"
ORIGINAL = Path("/workspaces/Public")
REVERIFY = Path(__file__).with_name("codespaces-reverify-enrolled-worker.py")
PYTHON = "/opt/public-chatgpt-mcp/venv/bin/python"
UPSTREAM = Path("/opt/public-chatgpt-mcp/source")
PINNED = "dec01b9f50f966097ddfc84d357d12a52f238935"
WORKER = "chatgpt-worker"
CONTROLLER = "chatgpt-controller"
NAME = "public-worker"
SERVER = "http://127.0.0.1:8765"

# Passed as a fixed no-secret script to an isolated worker via python -c.
# No enrollment arguments, no registration, no credential deletion or rewrite.
STRICT_WORKER_SOURCE = """
import asyncio
from pathlib import Path
from local_shell_mcp import remote

server = "http://127.0.0.1:8765"
workdir = "/srv/chatgpt-worker/worktrees/Public"
identity_path = Path("/srv/chatgpt-worker/state/identity.json")
identity = remote._read_worker_identity(server, "public-worker")
if not identity or identity_path.is_symlink() or identity.get("workdir") != workdir:
    raise SystemExit(61)

post_forever = remote._worker_post_json_forever
async def no_registration(url, *args, **kwargs):
    if str(url).split("?")[0].endswith("/register"):
        raise RuntimeError("registration prohibited during strict resume")
    return await post_forever(url, *args, **kwargs)
remote._worker_post_json_forever = no_registration

def no_identity_delete():
    raise RuntimeError("identity deletion prohibited during strict resume")
remote._delete_worker_identity = no_identity_delete

def no_identity_rewrite(data):
    if data != identity:
        raise RuntimeError("identity mutation prohibited during strict resume")
remote._write_worker_identity = no_identity_rewrite

async def strict_resume(url, payload, headers, timeout=None):
    if not str(url).split("?")[0].endswith("/resume"):
        raise RuntimeError("unexpected authentication endpoint")
    response = await asyncio.to_thread(remote._worker_post_json, url, payload, headers, timeout)
    if not isinstance(response, dict) or response.get("ok") is not True:
        raise RuntimeError("saved worker identity rejected; credentials preserved")
    return response
remote._worker_resume_or_none = strict_resume

asyncio.run(remote.run_worker(server, "", "public-worker", workdir))
"""


class Refusal(Exception):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Refusal(reason)


def private_json(path: Path, user: str) -> dict:
    require(path.is_file() and not path.is_symlink(), "persisted worker state missing")
    st = path.stat()
    require(st.st_uid == pwd.getpwnam(user).pw_uid
            and stat.S_IMODE(st.st_mode) == 0o600,
            "persisted worker state ownership/mode incorrect")
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), "persisted worker state invalid")
    return payload


def quiet(argv: list[str], timeout: int = 8) -> bool:
    return subprocess.run(
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=timeout, check=False,
    ).returncode == 0


def require_saved_identity() -> None:
    registration = private_json(REGISTRY, CONTROLLER)
    identity = private_json(IDENTITY, WORKER)
    config = private_json(CONFIG, WORKER)
    require(registration.get("version") == 1
            and isinstance(registration.get("workers"), list)
            and len(registration["workers"]) == 1
            and isinstance(registration["workers"][0], dict)
            and isinstance(registration.get("invites"), list),
            "exactly one registered worker required")
    record = registration["workers"][0]
    for value, expected in (
        (record.get("name"), NAME),
        (record.get("workdir"), str(WORKTREE)),
        (identity.get("name"), NAME),
        (identity.get("server"), SERVER),
        (identity.get("workdir"), str(WORKTREE)),
        (config.get("name"), NAME),
        (config.get("server"), SERVER),
        (config.get("workdir"), str(WORKTREE)),
    ):
        require(value == expected, "saved worker and registry bindings disagree")
    access = identity.get("access")
    registered_access = record.get("access")
    require(isinstance(access, str) and isinstance(registered_access, str)
            and access.startswith("lsmcp_wk_")
            and hmac.compare_digest(access, registered_access),
            "saved worker token does not match controller registration")


def healthy_controller() -> bool:
    try:
        with urlopen(SERVER + "/healthz", timeout=3) as response:
            return response.status == 200
    except (HTTPError, URLError, OSError):
        return False


def preflight() -> None:
    require(os.geteuid() == 0 and os.environ.get("SUDO_USER") == "codespace",
            "run with sudo from codespace account")
    require(len(sys.argv) == 1, "no arguments permitted")
    require(ORIGINAL.is_dir() and not ORIGINAL.is_symlink()
            and WORKTREE.is_dir() and not WORKTREE.is_symlink(),
            "expected Public worktrees missing")
    branch = subprocess.check_output(
        ["/usr/bin/git", "-C", str(ORIGINAL), "branch", "--show-current"],
        text=True, stderr=subprocess.DEVNULL, timeout=8).strip()
    origin = subprocess.check_output(
        ["/usr/bin/git", "-C", str(ORIGINAL), "remote", "get-url", "origin"],
        text=True, stderr=subprocess.DEVNULL, timeout=8).strip()
    require(branch == "experiments/chatgpt-workspace-qualification"
            and origin in ("https://github.com/Binilts03/Public",
                           "https://github.com/Binilts03/Public.git"),
            "only Public qualification branch authorized")
    upstream = subprocess.check_output(
        ["/usr/bin/git", "-C", str(UPSTREAM), "rev-parse", "HEAD"],
        text=True, stderr=subprocess.DEVNULL, timeout=8).strip()
    require(upstream == PINNED, "remote worker runtime source pin unexpected")
    require(healthy_controller(), "existing OAuth controller not healthy")
    require(quiet(["pgrep", "-u", CONTROLLER, "-f", "nondumpable_mcp_entrypoint.py"]),
            "OAuth controller process not running")
    require(not quiet(["pgrep", "-u", WORKER, "-f", "local_shell_mcp.remote_worker"])
            and not quiet(["pgrep", "-u", WORKER, "-f", "registration prohibited during strict resume"]),
            "worker process already present; do not duplicate")
    require(Path(PYTHON).is_file(), "backend interpreter unavailable")
    require(not quiet(["/usr/sbin/runuser", "-u", WORKER, "--",
                       "test", "-x", "/workspaces"]),
            "worker can traverse original or sibling workspaces")
    require(not quiet(["/usr/sbin/runuser", "-u", WORKER, "--",
                       "test", "-r", str(CTRL_ROOT / "controller.env")]),
            "worker can read OAuth credentials")
    require(quiet(["/usr/sbin/runuser", "-u", WORKER, "--",
                   "test", "-x", str(WORKTREE)]),
            "worker cannot access isolated Public worktree")
    for sock in ("/var/run/docker.sock", "/run/docker.sock"):
        if Path(sock).exists():
            require(not quiet(["/usr/sbin/runuser", "-u", WORKER, "--",
                               "test", "-r", sock])
                    and not quiet(["/usr/sbin/runuser", "-u", WORKER, "--",
                                   "test", "-w", sock]), "worker can use Docker socket")
    gitpush = subprocess.run(
        ["/usr/sbin/runuser", "-u", WORKER, "--",
         "/usr/bin/git", "-C", str(WORKTREE),
         "remote", "get-url", "--push", "origin"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=8, check=False)
    require(gitpush.returncode == 0 and gitpush.stdout.strip() == b"no-push://disabled",
            "worker origin push remote must remain disabled")
    require_saved_identity()
    require(REVERIFY.is_file() and not REVERIFY.is_symlink(),
            "existing worker requalification script missing")
    require(LOG.is_file() and not LOG.is_symlink(),
            "worker log missing; do not create it during recovery")
    st = LOG.stat()
    require(st.st_uid == pwd.getpwnam(WORKER).pw_uid
            and stat.S_IMODE(st.st_mode) == 0o600,
            "worker log has unsafe permissions")


def stop_only_child(child: subprocess.Popen) -> None:
    if child.poll() is not None:
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
        except ProcessLookupError:
            pass
    except ProcessLookupError:
        pass


def main() -> None:
    preflight()
    print("EXISTING_WORKER_CREDENTIAL_BINDING_PREFLIGHT_PASS", flush=True)
    env = {
        "HOME": str(ROOT / "home"),
        "XDG_CONFIG_HOME": str(ROOT / "home/.config"),
        "PATH": "/opt/public-chatgpt-mcp/venv/bin:/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "LOCAL_SHELL_MCP_WORKSPACE_ROOT": str(WORKTREE),
        "LOCAL_SHELL_MCP_WORKER_STATE_DIR": str(ROOT / "state"),
        "LOCAL_SHELL_MCP_STATE_DIR": str(ROOT / "state"),
        "LOCAL_SHELL_MCP_AGENT_CONFIG_DIR": str(ROOT / "skills"),
        "LOCAL_SHELL_MCP_REMOTE_ENABLED": "false",
        "LOCAL_SHELL_MCP_AUTH_MODE": "none",
        "LOCAL_SHELL_MCP_ALLOW_FULL_CONTAINER": "false",
        "LOCAL_SHELL_MCP_UI_ENABLED": "false",
        "LOCAL_SHELL_MCP_LIVE_WORKSPACE_ENABLED": "false",
    }
    argv = [
        "/usr/sbin/runuser", "-u", WORKER, "--", "/usr/bin/env", "-i",
        *[f"{name}={value}" for name, value in env.items()],
        PYTHON, "-c", STRICT_WORKER_SOURCE,
    ]
    fd = os.open(LOG, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    try:
        child = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=fd,
            stderr=subprocess.STDOUT, cwd=str(WORKTREE),
            start_new_session=True,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
    finally:
        os.close(fd)
    try:
        # This existing helper creates a temporary OAuth test client but does
        # not invite/enroll a worker; it proves actual remote stdout/denials.
        verified = subprocess.run(
            [PYTHON, str(REVERIFY)], cwd=str(ORIGINAL),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=75, check=False)
        require(child.poll() is None and verified.returncode == 0
                and b"EXISTING_WORKER_REMOTE_STDOUT_AND_DENIAL_PASS" in verified.stdout,
                "saved worker failed independent requalification")
        require_saved_identity()
    except BaseException:
        stop_only_child(child)
        raise
    print("EXISTING_WORKER_STRICT_RESUME_PASS", flush=True)
    print("WORKER_LEFT_RUNNING_NO_INVITE_NO_REENROLLMENT", flush=True)
    print("NO_GIT_WRITES_NO_PORT_CHANGES_NO_SECRETS_PRINTED", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never print arbitrary errors or log data: they may contain secrets.
        print("BLOCKED: strict worker resume failure class=" + type(exc).__name__
              + " (saved registration retained)", file=sys.stderr)
        raise SystemExit(2)
