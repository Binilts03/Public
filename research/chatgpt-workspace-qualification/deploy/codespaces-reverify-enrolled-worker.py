#!/usr/bin/env python3
"""Requalify EXISTING Codespaces MCP worker without inviting/enrolling another.

Reads protected worker/controller identity metadata locally as root.
Creates a short-lived OAuth test *client* to authenticate to localhost.
Does NOT issue a worker invitation, spawn/kill a worker, rewrite identity,
perform Git operations, expose ports, or modify any other repository.
DO NOT print source state, log lines, tokens or arbitrary exception strings.
"""
from __future__ import annotations

import asyncio
import hmac
import importlib.util
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys

ORIGINAL = Path("/workspaces/Public")
SCRIPT = Path(__file__).with_name("codespaces-enroll-verify-worker.py")
WORKER_ROOT = Path("/srv/chatgpt-worker")
CTRL_ROOT = Path("/srv/chatgpt-controller")
REGISTRY = CTRL_ROOT / "state/remote-workers.json"
IDENTITY = WORKER_ROOT / "state/identity.json"
CONFIG = WORKER_ROOT / "state/config.json"


class QualificationFailure(Exception):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise QualificationFailure(reason)


def private_json(path: Path, owner_name: str) -> dict:
    require(path.is_file() and not path.is_symlink(), "required persisted state missing")
    metadata = path.stat()
    require(
        metadata.st_uid == pwd.getpwnam(owner_name).pw_uid
        and stat.S_IMODE(metadata.st_mode) == 0o600,
        "persisted identity/registry ownership or mode invalid",
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "persisted state not an object")
    return value


def as_worker(argv: list[str]) -> bool:
    result = subprocess.run(
        ["/usr/sbin/runuser", "-u", "chatgpt-worker", "--", *argv],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=8, check=False,
    )
    return result.returncode == 0


def main() -> None:
    require(os.geteuid() == 0 and os.environ.get("SUDO_USER") == "codespace",
            "run with sudo from Codespaces owner only")
    require(len(sys.argv) == 1, "no arguments accepted")
    require(SCRIPT.is_file() and not SCRIPT.is_symlink(),
            "pinned qualification module unavailable")
    require(
        subprocess.run(
            ["pgrep", "-u", "chatgpt-worker", "-f", "local_shell_mcp.remote_worker"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        ).returncode == 0, "existing worker process not found",
    )
    require(not as_worker(["test", "-x", "/workspaces"]), "worker can traverse protected checkout parent")
    require(not as_worker(["test", "-r", str(CTRL_ROOT / "controller.env")]),
            "worker can read OAuth credentials")
    require(as_worker(["test", "-x", str(WORKER_ROOT / "worktrees/Public")]),
            "worker cannot enter authorized worktree")
    for socket in ("/var/run/docker.sock", "/run/docker.sock"):
        if Path(socket).exists():
            require(not as_worker(["test", "-r", socket]) and
                    not as_worker(["test", "-w", socket]),
                    "worker has Docker socket access")
    reg = private_json(REGISTRY, "chatgpt-controller")
    identity = private_json(IDENTITY, "chatgpt-worker")
    config = private_json(CONFIG, "chatgpt-worker")
    require(reg.get("version") == 1 and isinstance(reg.get("workers"), list),
            "invalid registry shape")
    workers = reg["workers"]
    require(len(workers) == 1 and isinstance(workers[0], dict),
            "expected exactly one enrolled worker; no mutation permitted")
    record = workers[0]
    required_name = "public-worker"
    expected_worktree = str(WORKER_ROOT / "worktrees/Public")
    for field, value in (
        (record.get("name"), required_name),
        (record.get("workdir"), expected_worktree),
        (identity.get("name"), required_name),
        (identity.get("workdir"), expected_worktree),
        (identity.get("server"), "http://127.0.0.1:8765"),
        (config.get("name"), required_name),
        (config.get("workdir"), expected_worktree),
        (config.get("server"), "http://127.0.0.1:8765"),
    ):
        require(field == value, "controller/worker identity binding mismatch")
    worker_access = identity.get("access")
    registered_access = record.get("access")
    require(
        isinstance(worker_access, str) and isinstance(registered_access, str)
        and worker_access.startswith("lsmcp_wk_")
        and hmac.compare_digest(worker_access, registered_access),
        "persisted worker access identity differs from controller registry",
    )
    require(not as_worker(["test", "-w", str(ORIGINAL)]),
            "worker can write original checkout")
    require(
        subprocess.run(
            ["/usr/sbin/runuser", "-u", "codespace", "--",
             "git", "-C", str(ORIGINAL), "status", "--porcelain"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=8, check=False,
        ).stdout == b"", "original checkout has uncommitted changes",
    )

    # Reuse the already pinned, independently tested OAuth + MCP verifier.
    spec = importlib.util.spec_from_file_location("public_enrollment_module", SCRIPT)
    require(spec is not None and spec.loader is not None, "module import unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    print("ENROLLED_WORKER_IDENTITY_BOUND_PASS: worker/registry identity and OS permissions")

    # A new OAuth *test client* is registered for verification; no new worker
    # invitation, worker registration, worker process, or Git write occurs.
    credentials = module.read_controller_credentials()
    token = module.local_oauth(
        credentials["LOCAL_SHELL_MCP_PUBLIC_BASE_URL"],
        credentials["LOCAL_SHELL_MCP_OAUTH_ADMIN_PIN"],
        credentials["LOCAL_SHELL_MCP_OAUTH_JWT_SECRET"],
    )
    print("EXISTING_WORKER_OAUTH_PKCE_PASS")
    result = asyncio.run(module.verify_remote(token, None))
    require(result.get("worker_online") is True, "MCP worker verification did not confirm online state")
    print("EXISTING_WORKER_REMOTE_STDOUT_AND_DENIAL_PASS")
    print("NO_WORKER_ENROLLMENT_NO_GIT_CHANGES_NO_PORT_CHANGES")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        # No secrets or arbitrary credential-bearing exception text.
        print("BLOCKED: existing worker requalification class=" +
              type(exc).__name__ + " (state preserved)", file=sys.stderr)
        raise SystemExit(2)
