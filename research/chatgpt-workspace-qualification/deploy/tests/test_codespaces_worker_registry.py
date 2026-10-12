"""Registry recovery gate regression; uses only disposable temporary files.

Import requires the pinned local-shell-mcp candidate venv (CI local-shell-mcp
job), but never starts a service or accesses a real Codespaces identity.
"""
from __future__ import annotations

import getpass
import importlib.util
import json
import os
from pathlib import Path
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "codespaces-enroll-verify-worker.py"


@pytest.fixture
def gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    spec = importlib.util.spec_from_file_location("codespaces_enrollment", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ctrl = tmp_path / "ctrl"
    worker = tmp_path / "worker"
    (ctrl / "state").mkdir(parents=True)
    (worker / "state").mkdir(parents=True)
    monkeypatch.setattr(module, "CTRL_ROOT", ctrl)
    monkeypatch.setattr(module, "WORKER_ROOT", worker)
    monkeypatch.setattr(module, "CTRL_USER", getpass.getuser())
    registry = ctrl / "state" / "remote-workers.json"

    def put(workers=None, invites=None, version=1):
        registry.write_text(json.dumps({
            "version": version,
            "workers": [] if workers is None else workers,
            "invites": [] if invites is None else invites,
        }))
        registry.chmod(0o600)

    return module, registry, worker, put


def test_clean_registry_passes(gate):
    module, registry, worker, put = gate
    put()
    module.require_clean_worker_registration()


@pytest.mark.parametrize("case", ["worker", "live_invite", "expired_invite", "invalid"])
def test_registry_guards(gate, case):
    module, registry, worker, put = gate
    if case == "worker":
        put(workers=[{"name": "public-worker", "access": "never-printed"}])
    elif case == "live_invite":
        put(invites=[{"code": "never-printed", "expires_at": time.time() + 7200}])
    elif case == "expired_invite":
        put(invites=[{"code": "never-printed", "expires_at": time.time() - 7200}])
        module.require_clean_worker_registration()
        return
    else:
        put(version=2)
    with pytest.raises(module.GateFailure):
        module.require_clean_worker_registration()


@pytest.mark.parametrize("filename", [
    "identity.json", "identity.json.tmp", "config.json", "config.json.tmp",
])
def test_worker_state_must_not_exist(gate, filename):
    module, registry, worker, put = gate
    put()
    (worker / "state" / filename).write_text("sealed-fixture")
    with pytest.raises(module.GateFailure):
        module.require_clean_worker_registration()


def test_registry_requires_private_mode_and_not_symlink(gate, tmp_path):
    module, registry, worker, put = gate
    put()
    registry.chmod(0o644)
    with pytest.raises(module.GateFailure):
        module.require_clean_worker_registration()
    registry.unlink()
    outside = tmp_path / "safe-fixture"
    outside.write_text("not-a-registry")
    registry.symlink_to(outside)
    with pytest.raises(module.GateFailure):
        module.require_clean_worker_registration()


def test_no_failed_invite_logging_or_restart_by_default():
    source = SCRIPT.read_text()
    assert "cwd=str(WORKTREE)" in source
    assert "require_clean_worker_registration()" in source
    assert "stop_our_worker(p)" in source
    assert "print(invite)" not in source
    assert "print(token)" not in source
    assert 'test ! -r /var/run/docker.sock' not in source


def test_remote_proof_reads_exact_stdout_not_echoed_command(gate):
    module, registry, worker, put = gate
    module.WORKTREE = worker / "worktrees/Public"
    expected = [
        module.WORKER_USER,
        str(module.WORKTREE),
        str(module.WORKTREE),
        module.EXPECTED_PUSH,
        "CTRL_SECRETS_HIDDEN",
        "ORIGINAL_REPO_PROTECTED",
        "ORIGINAL_REPO_TRAVERSAL_DENIED",
    ]
    good = {
        "exit_code": 0, "timed_out": False, "truncated": False,
        "stdout": "\n".join(expected) + "\n",
        "stderr": "",
        "command": "command under test",
    }
    module.verify_remote_stdout(good)

    # The real backend echoes the full command in the 'command' response field.
    # The original verifier incorrectly searched this field for PASS markers.
    fake = {
        **good,
        "stdout": "\n".join(expected[:4]) + "\n",
        "command": "\n".join(expected),
    }
    with pytest.raises(module.GateFailure):
        module.verify_remote_stdout(fake)

    for invalid in (
        {**good, "exit_code": 1},
        {**good, "timed_out": True},
        {**good, "truncated": True},
        {**good, "stdout": None},
        {**good, "stdout": good["stdout"].replace(
            "CTRL_SECRETS_HIDDEN\n", "",
        )},
        {**good, "stdout": good["stdout"] + "UNEXPECTED\n"},
    ):
        with pytest.raises(module.GateFailure):
            module.verify_remote_stdout(invalid)


def test_requalification_reuses_worker_not_invitation():
    reverify = ROOT / "codespaces-reverify-enrolled-worker.py"
    src = reverify.read_text(encoding="utf-8")
    assert "module.verify_remote(token, None)" in src
    assert "private_json(IDENTITY" in src
    assert "hmac.compare_digest(worker_access, registered_access)" in src
    assert "EXISTING_WORKER_REMOTE_STDOUT_AND_DENIAL_PASS" in src
    assert "module.local_oauth(" in src
    for danger in ("spawn_worker(", "create_invite(", "remote_manage\", {\"action\": \"invite",
                   "git push", "os.killpg(", "chmod(", "chown("):
        assert danger not in src, danger
