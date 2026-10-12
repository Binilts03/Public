"""Offline regression tests for safe restart of a registered Codespaces worker."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import pwd
import os

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "codespaces-resume-enrolled-worker.py"
spec = importlib.util.spec_from_file_location("codespaces_resume_existing", SCRIPT)
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_saved_worker_state_is_bound_to_one_registration(tmp_path, monkeypatch):
    ctrl = tmp_path / "ctrl.json"
    identity = tmp_path / "identity.json"
    config = tmp_path / "config.json"
    worker_path = tmp_path / "public-worker"
    account = pwd.getpwuid(os.getuid()).pw_name
    monkeypatch.setattr(m, "REGISTRY", ctrl)
    monkeypatch.setattr(m, "IDENTITY", identity)
    monkeypatch.setattr(m, "CONFIG", config)
    monkeypatch.setattr(m, "WORKTREE", worker_path)
    monkeypatch.setattr(m, "WORKER", account)
    monkeypatch.setattr(m, "CONTROLLER", account)
    reference = "synthetic-worker-fixture"
    saved = {"name": m.NAME, "server": m.SERVER,
             "workdir": str(worker_path)}
    registry = {"version": 1, "workers": [
        {"name": m.NAME, "workdir": str(worker_path), "access": reference}
    ], "invites": []}
    saved_identity = {**saved, "access": reference}

    def write_state():
        for path, record in ((ctrl, registry), (identity, saved_identity),
                             (config, saved)):
            path.write_text(json.dumps(record))
            path.chmod(0o600)

    write_state()
    with pytest.raises(m.Refusal):
        m.require_saved_identity()
    saved_identity["access"] = "lsmcp_wk_fixture"
    registry["workers"][0]["access"] = "lsmcp_wk_fixture"
    write_state()
    m.require_saved_identity()
    registry["workers"].append(dict(registry["workers"][0]))
    write_state()
    with pytest.raises(m.Refusal):
        m.require_saved_identity()
    registry["workers"].pop()
    write_state()
    identity.chmod(0o644)
    with pytest.raises(m.Refusal):
        m.require_saved_identity()


def test_resume_restricts_registration_and_keeps_permissions():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "async def no_registration" in source
    assert "async def strict_resume" in source
    assert "def no_identity_delete" in source
    assert "def no_identity_rewrite" in source
    assert "remote.run_worker(server, \"\", \"public-worker\", workdir)" in source
    assert "EXISTING_WORKER_STRICT_RESUME_PASS" in source
    assert "EXISTING_WORKER_REMOTE_STDOUT_AND_DENIAL_PASS" in source
    assert "local_shell_mcp.remote_worker" in m.STRICT_WORKER_SOURCE
    assert "stop_only_child(child)" in source
    assert '"LOCAL_SHELL_MCP_ALLOW_FULL_CONTAINER": "false"' in source
