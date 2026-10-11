#!/usr/bin/env python3
"""Read-only Codespaces /workspaces ACL investigation for the restricted worker.

This script inspects ONLY /workspaces and its immediate entries. It never
traverses into other repositories, reads their contents, changes ACLs, runs
Git, creates files, enrolls workers, or accesses OAuth credentials.
Only metadata about paths that the worker can write/traverse is reported.
Run: sudo python3 research/chatgpt-workspace-qualification/deploy/codespaces-diagnose-workspaces.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys

ROOT = Path("/workspaces")
ORIGINAL = ROOT / "Public"
WORKER = "chatgpt-worker"


def accessible(path: Path, flag: str) -> bool:
    try:
        return subprocess.run(
            ["runuser", "-u", WORKER, "--", "test", flag, str(path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=5, check=False,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("worker access probe could not complete") from None


def mode_info(path: Path) -> dict:
    lstat = path.lstat()
    try:
        target = path.stat()
    except OSError:
        target = None
    return {
        "kind": ("symlink" if stat.S_ISLNK(lstat.st_mode)
                 else "directory" if stat.S_ISDIR(lstat.st_mode)
                 else "other"),
        "owner_uid": lstat.st_uid,
        "group_gid": lstat.st_gid,
        "mode": oct(stat.S_IMODE(lstat.st_mode)),
        "target_mode": (oct(stat.S_IMODE(target.st_mode)) if target else None),
    }


def report_one(path: Path) -> dict:
    details = mode_info(path)
    details.update({
        "path": str(path),  # path names ONLY, not directory contents
        "worker_r": accessible(path, "-r"),
        "worker_w": accessible(path, "-w"),
        "worker_x": accessible(path, "-x"),
    })
    return details


def main() -> int:
    if os.geteuid() != 0 or os.environ.get("SUDO_USER") != "codespace":
        print("BLOCKED: run only with sudo from the Codespaces owner")
        return 2
    if not ROOT.is_dir() or not ORIGINAL.is_dir():
        print("BLOCKED: expected /workspaces/Public checkout missing")
        return 2
    pwd.getpwnam(WORKER)
    entries = sorted(ROOT.iterdir(), key=lambda p: p.name)
    if len(entries) > 100:
        print("BLOCKED: unexpected number of workspace entries; no traversal performed")
        return 2
    root = report_one(ROOT)
    original = report_one(ORIGINAL)
    flagged = []
    for child in entries:
        if child == ORIGINAL:
            continue
        # A directory symlink is still an entry that can expose some other path.
        if not child.is_dir():
            continue
        detail = report_one(child)
        if detail["worker_w"] or detail["worker_x"] or detail["worker_r"]:
            flagged.append(detail)
    print("WORKSPACE_ACCESS_DIAG_V1 — READ ONLY")
    print("root_access=" + json.dumps(root, sort_keys=True))
    print("original_access=" + json.dumps(original, sort_keys=True))
    for value in flagged:
        print("other_entry=" + json.dumps(value, sort_keys=True))
    print(f"other_entries_count={len(entries)-int(ORIGINAL in entries)}")
    print(f"other_accessible_entries={len(flagged)}")
    if root["worker_w"]:
        print("BLOCKER_ROOT: worker can write /workspaces itself; individual ACLs are insufficient")
    for item in flagged:
        if item["worker_w"]:
            print("BLOCKER_SIBLING: worker has write permission to a different workspace entry")
    print("NO_FILES_READ_NO_ACL_WRITES_NO_GIT_MUTATIONS_NO_PORT_CHANGES")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, KeyError):
        print("BLOCKED: unable to complete read-only workspace access inventory")
        raise SystemExit(2)
