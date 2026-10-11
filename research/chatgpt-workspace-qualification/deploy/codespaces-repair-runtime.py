#!/usr/bin/env python3
"""Conservatively repair unreadable *public-code* venv after Stage 2 umask 077.

Never touches OAuth secrets, worker files, Codespaces Git checkout, account
membership, public ingress, or running services. Validates entire venv before
chmod, then permits non-root users to read/execute only root-owned runtime code.
"""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import socket
import stat
import subprocess
import sys

ROOT = Path("/opt/public-chatgpt-mcp")
VENV = ROOT / "venv"
QUALIFIED = ROOT / "codespaces-isolation-qualified"
WORKSPACE = Path("/workspaces/Public")
CTRL = "chatgpt-controller"
WORKER = "chatgpt-worker"
CTRL_ROOT = Path("/srv/chatgpt-controller")
WORKER_ROOT = Path("/srv/chatgpt-worker")


class Blocked(RuntimeError):
    pass


def require(ok: bool, why: str) -> None:
    if not ok:
        raise Blocked(why)


def run_as(user: str, command: list[str]) -> bool:
    try:
        return subprocess.run(
            ["runuser", "-u", user, "--", *command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def permissions(node: Path) -> os.stat_result:
    value = node.lstat()
    require(value.st_uid == 0, "runtime entry not root-owned; no permissions changed")
    require(stat.S_ISDIR(value.st_mode) or stat.S_ISREG(value.st_mode),
            "nonstandard runtime entry encountered; no permissions changed")
    return value


def permitted_symlink(node: Path, root: Path) -> bool:
    try:
        resolved = node.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    # Standard venv Python symlinks can point to system-owned interpreters.
    for prefix in (root, Path("/usr"), Path("/bin"), Path("/lib"), Path("/lib64")):
        if resolved == prefix or prefix in resolved.parents:
            return True
    return False


def repair_public_code_venv(venv: Path) -> int:
    """Validate first; then modify only directories and regular files in venv.

    Deliberately accepts a venv path for CI's throwaway fixture. All real-host
    entrypoint constraints are checked independently in main().
    """
    require(venv.is_dir() and not venv.is_symlink(), "venv absent or symlink")
    real_root = venv.resolve(strict=True)
    entries: list[tuple[Path, os.stat_result]] = []
    for here, dirs, files in os.walk(venv, followlinks=False):
        for candidate in [Path(here), *(Path(here) / x for x in dirs + files)]:
            mode = candidate.lstat().st_mode
            if stat.S_ISLNK(mode):
                require(permitted_symlink(candidate, real_root),
                        "unexpected runtime symlink outside allowlist; no permissions changed")
                continue
            entries.append((candidate, permissions(candidate)))

    for candidate, value in entries:
        mode = stat.S_IMODE(value.st_mode)
        target = mode | stat.S_IRGRP | stat.S_IROTH
        if stat.S_ISDIR(value.st_mode) or mode & stat.S_IXUSR:
            target |= stat.S_IXGRP | stat.S_IXOTH
        target &= ~(stat.S_IWGRP | stat.S_IWOTH)
        if target != mode:
            os.chmod(candidate, target, follow_symlinks=False)
    return len(entries)


def main() -> int:
    require(os.geteuid() == 0 and os.environ.get("SUDO_USER") == "codespace",
            "run only as sudo python3 from the codespace login")
    require(len(sys.argv) == 1, "no positional arguments accepted")
    require(QUALIFIED.is_file() and QUALIFIED.stat().st_uid == 0
            and stat.S_IMODE(QUALIFIED.stat().st_mode) == 0o600,
            "previous isolated deployment has not been qualified")
    require(ROOT.is_dir() and ROOT.stat().st_uid == 0 and not ROOT.is_symlink(),
            "root-owned staged runtime not found")
    require(VENV.is_dir() and VENV.stat().st_uid == 0 and not VENV.is_symlink(),
            "expected root-owned venv absent")
    require(CTRL_ROOT.is_dir() and WORKER_ROOT.is_dir(),
            "existing controller/worker state not found")
    for user in (CTRL, WORKER):
        require(pwd.getpwnam(user).pw_uid != 0, "invalid system identity")
        require(not run_as(user, ["test", "-r", str(CTRL_ROOT / "state")]) if user == WORKER else True,
                "worker can read controller state")
    require(not run_as(WORKER, ["test", "-x", str(WORKSPACE)]),
            "worker can traverse original Codespaces checkout")
    require(not run_as(WORKER, ["test", "-w", str(WORKSPACE)]),
            "worker can write original Codespaces checkout")
    require(not run_as(WORKER, ["test", "-r", str(CTRL_ROOT / "controller.env")]),
            "worker can read OAuth credentials")
    require(stat.S_IMODE((CTRL_ROOT / "controller.env").stat().st_mode) == 0o600,
            "controller credentials mode is not 0600")
    require((CTRL_ROOT / "controller.env").stat().st_uid == pwd.getpwnam(CTRL).pw_uid,
            "controller credential ownership is not correct")
    for user in (CTRL, WORKER):
        proc = subprocess.run(["pgrep", "-u", user], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, check=False)
        require(proc.returncode != 0, "controller or worker process is running; refuse live update")
    with socket.socket() as sock:
        sock.settimeout(0.5)
        require(sock.connect_ex(("127.0.0.1", 8765)) != 0,
                "port 8765 already has a listener; refuse live update")

    python = VENV / "bin/python"
    require(python.exists(), "venv executable absent")
    print("RUNTIME_REPAIR_PREFLIGHT_PASS: existing isolated identities, secrets and inactive controller validated")
    prior = run_as(CTRL, [str(python), "-c", "import local_shell_mcp.main"])
    print("CONTROLLER_IMPORT_BEFORE:", "PASS" if prior else "DENIED_OR_FAILED")
    count = repair_public_code_venv(VENV)
    require(run_as(CTRL, [str(python), "-c", "import local_shell_mcp.main"]),
            "controller import still fails; private diagnostics needed")
    require(run_as(WORKER, [str(python), "-c", "import local_shell_mcp.remote_worker"]),
            "worker import still fails; private diagnostics needed")
    require(not run_as(WORKER, ["test", "-r", str(CTRL_ROOT / "controller.env")]),
            "OAuth file boundary regressed")
    require(not run_as(WORKER, ["test", "-w", str(WORKSPACE)]),
            "original workspace access boundary regressed")
    print(f"RUNTIME_PERMISSIONS_REPAIRED_PASS: {count} venv code nodes checked; controller and worker imports PASS")
    print("NO_SECRETS_CHANGED_NO_PROCESS_STARTED_NO_PORT_EXPOSED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Blocked, OSError, KeyError) as exc:
        # Deliberately omit exception text: malformed path/env errors may expose data.
        if isinstance(exc, Blocked):
            print("BLOCKED:", str(exc), file=sys.stderr)
        else:
            print("BLOCKED: unexpected host condition; inspect privately", file=sys.stderr)
        raise SystemExit(2)
