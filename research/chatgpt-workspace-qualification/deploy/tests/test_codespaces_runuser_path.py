#!/usr/bin/env python3
"""Regression: absolute runuser launch survives a deliberately restricted PATH.

On an ephemeral Ubuntu CI runner only. No network, worktree, service,
configuration or credential changes. Sudo is used solely to test UID drop
to the system 'nobody' account.
"""
from __future__ import annotations

import ast
import errno
import os
from pathlib import Path
import pwd
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNUSER = Path("/usr/sbin/runuser")
RESTRICTED = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}


def main() -> None:
    assert os.geteuid() == 0, "Fixture must be run with sudo in ephemeral CI"
    assert RUNUSER.is_file() and os.access(RUNUSER, os.X_OK)
    assert RUNUSER.stat().st_uid == 0
    assert not (stat.S_IMODE(RUNUSER.stat().st_mode) & 0o022), "runuser writable by non-root"
    assert pwd.getpwnam("nobody").pw_uid != 0

    # Reproduce prior Codespaces failure: child environment excludes /usr/sbin.
    try:
        subprocess.run(
            ["runuser", "--version"],
            cwd="/tmp", env=RESTRICTED,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=5, check=True,
        )
    except FileNotFoundError as exc:
        assert exc.errno == errno.ENOENT
    else:
        raise AssertionError("Expected original missing-executable failure under restricted PATH")

    # Corrected executable cannot depend on the child's PATH.
    test = subprocess.run(
        [str(RUNUSER), "-u", "nobody", "--", "/usr/bin/id", "-un"],
        cwd="/tmp", env=RESTRICTED,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=8, check=False,
    )
    assert test.returncode == 0, "absolute runuser could not execute under restricted PATH"
    assert test.stdout.strip() == b"nobody", "did not drop to expected unprivileged UID"

    for basename in ("codespaces-probe-worker-launch.py", "codespaces-enroll-verify-worker.py"):
        text = (ROOT / basename).read_text(encoding="utf-8")
        ast.parse(text)
        assert 'RUNUSER = Path("/usr/sbin/runuser")' in text
        assert "str(RUNUSER)" in text
        assert '"runuser"' not in text, f"{basename} retains an unsafe basename lookup"
        assert '"PATH": "/usr/bin:/bin"' in text, "restricted environment was weakened"
        assert "root-owned /usr/sbin/runuser missing or not executable" in text

    print("CODESPACES_RUNUSER_RESTRICTED_PATH_REGRESSION_PASS")
    print("NO_HOST_CONFIG_CHANGE_NO_WORKER_ENROLLMENT_NO_CREDENTIAL_ACCESS")


if __name__ == "__main__":
    main()
