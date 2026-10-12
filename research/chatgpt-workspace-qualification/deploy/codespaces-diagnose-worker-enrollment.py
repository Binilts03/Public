#!/usr/bin/env python3
"""READ-ONLY Codespaces worker enrollment failure diagnosis.

Never prints worker logs, OAuth tokens, invitations, registration IDs, process
environment, or contents of state files (all may contain credentials).
Reads only expected service log and state metadata; fixed diagnostic categories.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

WORKER = "chatgpt-worker"
CTRL = "chatgpt-controller"
WORKER_ROOT = Path("/srv/chatgpt-worker")
CTRL_ROOT = Path("/srv/chatgpt-controller")
IDENTITY = WORKER_ROOT / "state/identity.json"
CONFIG = WORKER_ROOT / "state/config.json"
LOG = WORKER_ROOT / "logs/worker.log"
REGISTRY = CTRL_ROOT / "state/remote-workers.json"
active_process_cache = [False]


def report_path(label: str, path: Path) -> None:
    try:
        item = path.lstat()
    except OSError:
        print(label + "=ABSENT")
        return
    kind = ("SYMLINK" if stat.S_ISLNK(item.st_mode)
            else "FILE" if stat.S_ISREG(item.st_mode)
            else "DIRECTORY" if stat.S_ISDIR(item.st_mode) else "OTHER")
    owner = ("worker" if item.st_uid == pwd.getpwnam(WORKER).pw_uid
             else "controller" if item.st_uid == pwd.getpwnam(CTRL).pw_uid
             else "root" if item.st_uid == 0 else "OTHER")
    print(f"{label}={kind},owner={owner},mode={stat.S_IMODE(item.st_mode):03o},size={item.st_size}")


def access(user: str, flag: str, path: str) -> bool:
    try:
        res = subprocess.run(
            ["runuser", "-u", user, "--", "test", flag, path],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=5, check=False,
        )
        return res.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def active(user: str, pattern: str) -> bool:
    try:
        return subprocess.run(
            ["pgrep", "-u", user, "-f", pattern],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=4, check=False,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def health() -> str:
    try:
        with urlopen("http://127.0.0.1:8765/healthz", timeout=3) as response:
            return str(response.status)
    except HTTPError as exc:
        return str(exc.code)
    except (URLError, OSError, TimeoutError):
        return "UNREACHABLE"


def classify_log() -> None:
    if not LOG.is_file() or LOG.is_symlink():
        print("worker_log_categories=ABSENT")
        return
    try:
        # Cap reading and process only the suffix; never print any input lines.
        with LOG.open("rb") as stream:
            stream.seek(max(0, LOG.stat().st_size - 256000))
            data = stream.read(256000).decode("utf-8", errors="replace")
    except OSError:
        print("worker_log_categories=UNREADABLE")
        return
    fixed = {
        "permission_denied": r"permission denied|permissionerror",
        "cannot_get_cwd": r"getcwd|current working directory",
        "cannot_traverse_workspace": r"/workspaces/public|/workspaces",
        "incorrect_login_shell": r"cannot set.*user|runuser:",
        "cannot_access_state": r"state/identity.json|state/config.json",
        "invalid_invite": r"invalid invite|expired invite",
        "controller_auth_error": r"unauthorized|http 401|http 403",
        "backend_connection_error": r"connection refused|connecterror|cannot connect",
        "missing_module": r"modulenotfounderror|importerror",
        "missing_file": r"filenotfounderror",
        "argument_error": r"unrecognized arguments|systemexit: 2",
        "registry_error": r"already registered|already exists|invalid worker identity",
        "unexpected_python_error": r"traceback \(most recent call last\)",
    }
    match = [name for name, pat in fixed.items()
             if re.search(pat, data, re.IGNORECASE)]
    print("worker_log_categories=" + (",".join(match) if match else "UNKNOWN"))
    known = ("PermissionError", "FileNotFoundError", "ModuleNotFoundError",
             "ConnectionError", "RuntimeError", "ValueError", "KeyError",
             "BrokenPipeError", "OSError", "SystemExit", "TypeError",
             "AttributeError", "AssertionError")
    present = [typ for typ in known if re.search(r"\b" + typ + r"\b", data)]
    print("worker_log_exception_classes=" + (",".join(present) if present else "NONE_DETECTED"))
    print("worker_log_traceback=" + ("YES" if "Traceback (most recent call last)" in data else "NO"))


def registry_counts() -> None:
    """Report counts only; NEVER print invite codes or worker access tokens."""
    if not REGISTRY.is_file() or REGISTRY.is_symlink():
        print("controller_registry_valid=NO")
        print("safe_to_attempt_new_enrollment=NO")
        return
    try:
        item = REGISTRY.stat()
        expected_owner = pwd.getpwnam(CTRL).pw_uid
        if item.st_uid != expected_owner or stat.S_IMODE(item.st_mode) != 0o600:
            raise ValueError("bad registry owner or mode")
        payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("invalid registry version")
        workers, invites = payload.get("workers"), payload.get("invites")
        if not isinstance(workers, list) or not isinstance(invites, list):
            raise ValueError("invalid registry shape")
        if any(not isinstance(x, dict) for x in workers + invites):
            raise ValueError("invalid registry record")
        now = time.time()
        # The upstream registry stores invites as {code, expires_at, ...}.
        # Do not inspect or display code/token values.
        active = sum(
            float(row.get("expires_at", 0)) > now and not row.get("used", False)
            for row in invites
        )
        print("controller_registry_valid=YES")
        print("controller_registered_workers_count=" + str(len(workers)))
        print("controller_unexpired_invites_count=" + str(active))
        print("controller_expired_invites_count=" + str(len(invites)-active))
        clean = (
            not workers and not active
            and not IDENTITY.exists() and not CONFIG.exists()
            and not active_process_cache[0]
        )
        print("safe_to_attempt_new_enrollment=" + ("YES" if clean else "NO"))
    except (OSError, ValueError, TypeError, OverflowError):
        print("controller_registry_valid=NO")
        print("safe_to_attempt_new_enrollment=NO")


def main() -> int:
    if os.geteuid() != 0 or os.environ.get("SUDO_USER") != "codespace":
        print("BLOCKED: run via sudo python3 from Codespaces login")
        return 2
    if len(sys.argv) != 1:
        print("BLOCKED: no arguments accepted")
        return 2
    print("CODESPACES_WORKER_ENROLLMENT_DIAG_V1_READ_ONLY")
    print("controller_health_http=" + health())
    print("controller_process=" + ("YES" if active(CTRL, "nondumpable_mcp_entrypoint.py") else "NO"))
    active_process_cache[0] = active(WORKER, "local_shell_mcp.remote_worker")
    print("worker_process=" + ("YES" if active_process_cache[0] else "NO"))
    for label, item in (
        ("worker_identity", IDENTITY),
        ("worker_config", CONFIG),
        ("worker_log", LOG),
        ("controller_registry", REGISTRY),
    ):
        report_path(label, item)
    classify_log()
    registry_counts()
    print("worker_can_traverse_original_workspace=" +
          ("YES" if access(WORKER, "-x", "/workspaces/Public") else "NO"))
    print("worker_can_write_workspace_parent=" +
          ("YES" if access(WORKER, "-w", "/workspaces") else "NO"))
    print("worker_can_access_own_worktree=" +
          ("YES" if access(WORKER, "-x", str(WORKER_ROOT / "worktrees/Public")) else "NO"))
    print("worker_can_read_controller_credentials=" +
          ("YES" if access(WORKER, "-r", str(CTRL_ROOT / "controller.env")) else "NO"))
    # Verify the root launch location without exploring any other repositories.
    cwd = Path.cwd()
    print("diagnostic_started_inside_protected_checkout=" +
          ("YES" if cwd == Path("/workspaces/Public") else "NO"))
    print("NO_SECRETS_PRINTED_NO_GIT_ACTIONS_NO_NEW_INVITES_NO_SERVICE_CHANGES")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, RuntimeError):
        print("BLOCKED: diagnostic could not inspect host metadata", file=sys.stderr)
        raise SystemExit(2)
