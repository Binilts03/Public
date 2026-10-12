#!/usr/bin/env python3
"""Codespaces worker launcher preflight WITHOUT enrollment, invites or secrets.

It verifies the exact worker account, interpreter, sanitized env, allowed CWD,
runuser process hop, and a synthetic stdin pipe. No network connections, MCP
controller calls, Git mutations, worker state modifications, or logging files.
Reports fixed stage/error classes only; never prints subprocess stderr.
"""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys

WORKER = "chatgpt-worker"
WORKTREE = Path("/srv/chatgpt-worker/worktrees/Public")
PYTHON = Path("/opt/public-chatgpt-mcp/venv/bin/python")
# Avoid PATH lookup under the intentionally restricted launcher environment.
RUNUSER = Path("/usr/sbin/runuser")
CTRL_ENV = Path("/srv/chatgpt-controller/controller.env")
REGISTRY = Path("/srv/chatgpt-controller/state/remote-workers.json")
STATE = Path("/srv/chatgpt-worker/state")
EXACT_ORIGIN = "https://github.com/Binilts03/Public.git"


class Blocked(Exception):
    pass


def require(ok: bool, msg: str) -> None:
    if not ok:
        raise Blocked(msg)


def execute_probe(name: str, argv: list[str], stdin: bytes = b"") -> bool:
    """Check command's *expected* stdout only; suppress arbitrary stderr."""
    env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
    try:
        result = subprocess.run(
            argv,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=str(WORKTREE),
            start_new_session=True,
            timeout=12,
            check=False,
        )
    except OSError as exc:
        print(f"{name}=FAIL:spawn:{type(exc).__name__}:errno_{exc.errno}")
        return False
    except subprocess.TimeoutExpired:
        print(f"{name}=FAIL:timeout")
        return False
    if result.returncode != 0:
        print(f"{name}=FAIL:exit_code_{result.returncode}")
        return False
    if result.stdout != b"PASS\n":
        print(f"{name}=FAIL:unexpected_output")
        return False
    print(f"{name}=PASS")
    return True


def main() -> int:
    require(os.geteuid() == 0 and os.environ.get("SUDO_USER") == "codespace",
            "run with sudo from Codespaces account")
    require(len(sys.argv) == 1, "no parameters permitted")
    require(WORKTREE.is_dir() and not WORKTREE.is_symlink(), "isolated Public worktree missing")
    require(CTRL_ENV.is_file() and stat.S_IMODE(CTRL_ENV.stat().st_mode) == 0o600,
            "controller secret permission unexpected")
    require(PYTHON.exists(), "pinned Python runtime not present")
    require(RUNUSER.is_file() and os.access(RUNUSER, os.X_OK)
            and RUNUSER.stat().st_uid == 0,
            "root-owned /usr/sbin/runuser missing or not executable")
    worker_uid = pwd.getpwnam(WORKER).pw_uid
    require(worker_uid != 0, "worker cannot be root")
    require(
        subprocess.run(["pgrep", "-u", WORKER],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False).returncode != 0,
        "worker process already running",
    )
    # These tests run without any Git metadata reads and never create files.
    def denied(test_flag: str, location: str) -> bool:
        return subprocess.run([str(RUNUSER), "-u", WORKER, "--", "test",
                               test_flag, location],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              check=False).returncode != 0
    require(denied("-x", "/workspaces"), "worker can traverse protected workspace parent")
    require(denied("-r", str(CTRL_ENV)), "worker can read OAuth credentials")
    require(not denied("-x", str(WORKTREE)), "worker cannot traverse own worktree")
    for file in ("identity.json", "identity.json.tmp", "config.json", "config.json.tmp"):
        require(not (STATE / file).exists(),
                "persistent worker identity/config exists; do not start an enrollment")
    print("WORKER_LAUNCH_PREFLIGHT_V1_NO_ENROLLMENT")
    print("worker_uid_and_workspace_acl=PASS")
    base = [str(RUNUSER), "-u", WORKER, "--", "env", "-i",
            "HOME=/srv/chatgpt-worker/home",
            "XDG_CONFIG_HOME=/srv/chatgpt-worker/home/.config",
            "PATH=/opt/public-chatgpt-mcp/venv/bin:/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE=1",
            "LOCAL_SHELL_MCP_WORKER_STATE_DIR=/srv/chatgpt-worker/state",
            "LOCAL_SHELL_MCP_STATE_DIR=/srv/chatgpt-worker/state",
            "LOCAL_SHELL_MCP_WORKSPACE_ROOT=/srv/chatgpt-worker/worktrees/Public",
            "LOCAL_SHELL_MCP_REMOTE_ENABLED=false",
            "LOCAL_SHELL_MCP_AUTH_MODE=none",
            str(PYTHON)]
    # This should have *identical* OS launch mechanics to the actual runuser
    # worker while never invoking its connect/enrollment CLI.
    allowed = execute_probe("worker_runuser_python", base + [
        "-c",
        "import os,sys; print('PASS' if os.geteuid()!=0 and os.getcwd()=='/srv/chatgpt-worker/worktrees/Public' else 'FAIL')",
    ])
    if not allowed:
        print("DO_NOT_ENROLL: fix worker subprocess launch first")
        return 2
    imports = execute_probe("worker_backend_import", base + [
        "-c",
        "import local_shell_mcp.remote_worker; print('PASS')",
    ])
    if not imports:
        print("DO_NOT_ENROLL: worker Python runtime import failed")
        return 2
    piped = execute_probe("worker_private_stdin_pipe", base + [
        "-c",
        "import sys; print('PASS' if sys.stdin.readline().strip()=='synthetic-canary' else 'FAIL')",
    ], b"synthetic-canary\n")
    if not piped:
        print("DO_NOT_ENROLL: stdin/process handoff failed")
        return 2
    print("WORKER_LAUNCH_OS_GATES_PASS_NO_ENROLLMENT")
    print("NO_CONTROLLER_REQUESTS_NO_INVITES_NO_GIT_ACTIONS_NO_SECRETS_NO_PORT_CHANGES")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Blocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        # No exception .str: it can contain untrusted process or path content.
        print("BLOCKED: unexpected launch probe failure " + type(exc).__name__,
              file=sys.stderr)
        raise SystemExit(2)
