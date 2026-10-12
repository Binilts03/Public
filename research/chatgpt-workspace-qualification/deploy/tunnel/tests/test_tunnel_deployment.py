"""Offline qualification of the pinned Public Codespaces tunnel deployment.

No GitHub release downloaded; no API key provisioned; no worker enrollment;
no system account or ACL edits. Exercises local bytes and synthetic ZIPs only.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
from pathlib import Path
import stat
import zipfile

import pytest

HERE = Path(__file__).resolve().parents[1]
SCRIPT = HERE / "manage.py"
spec = importlib.util.spec_from_file_location("public_tunnel_management", SCRIPT)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_exact_dcr_profile_and_runtime_key_indirection():
    profile = (HERE / "profile.yaml").read_text()
    m.validate_profile(profile)
    assert profile == m.PROFILE_TEXT
    assert m.TUNNEL_ID == "tunnel_6acd09e0298481919ac84778501b0aef"
    assert "env:CONTROL_PLANE_API_KEY" in profile
    assert "http://127.0.0.1:8765/mcp" in profile
    assert "127.0.0.1:8770" in profile
    assert "tunnel_6acd09e0298481919ac84778501b0aef" in profile
    assert not any(x in profile for x in ("OPENAI_ADMIN_KEY", "sk-proj-", "sk-", "localhost:8765/oauth/authorize"))
    for bad in (
        profile.replace("env:CONTROL_PLANE_API_KEY", "sk-secret-committed"),
        profile.replace("127.0.0.1:8770", "0.0.0.0:8770"),
        profile.replace("127.0.0.1:8765", "0.0.0.0:8765"),
        profile.replace(m.TUNNEL_ID, "tunnel_" + "0"*32),
        profile.replace("open_browser: false", "open_browser: true"),
    ):
        with pytest.raises(m.Refusal):
            m.validate_profile(bad)


def asset(payloads=None, *, symlink=False):
    files = {name: (name + "\n").encode() for name in m.EXPECTED_FILES}
    if payloads:
        files.update(payloads)
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        for name, value in sorted(files.items()):
            info = zipfile.ZipInfo(name)
            if symlink and name == "tunnel-client":
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            else:
                info.external_attr = (stat.S_IFREG | 0o644) << 16
            z.writestr(info, value)
    return data.getvalue()


def test_release_hash_fails_closed_on_untrusted_archive():
    payload = asset()
    with pytest.raises(m.Refusal, match="digest"):
        m.read_release_zip(payload)
    assert m.RELEASE == "v0.0.15"
    assert m.ASSET == "tunnel-client-v0.0.15-linux-amd64.zip"
    assert m.DIGEST == "8c836dc5d68d68b663d9a5c5b28ff9fa780d9f7a3fffb1c306880b8f32fab5f1"


def test_zip_member_allowlist_and_symlink_refusal(monkeypatch):
    good = asset()
    monkeypatch.setattr(m, "DIGEST", hashlib.sha256(good).hexdigest())
    assert set(m.read_release_zip(good)) == m.EXPECTED_FILES
    bad = asset(symlink=True)
    monkeypatch.setattr(m, "DIGEST", hashlib.sha256(bad).hexdigest())
    with pytest.raises(m.Refusal, match="nonregular"):
        m.read_release_zip(bad)
    unexpected = asset({"unrelated-secret-file": b"x"})
    monkeypatch.setattr(m, "DIGEST", hashlib.sha256(unexpected).hexdigest())
    with pytest.raises(m.Refusal, match="member list"):
        m.read_release_zip(unexpected)


def test_staging_is_manual_no_model_api_no_external_port_mutation():
    source = SCRIPT.read_text()
    for assertion in (
        "cmd_install()", "cmd_key()", "cmd_client(verb)",
        "runuser", "chatgpt-tunnel", "no-create-home",
        "setfacl", "127.0.0.1", "NO_PROXY", "CONTROL_PLANE_API_KEY",
        "MAX_ARCHIVE", "os.O_NOFOLLOW", "getpass.getpass",
        "only the Public qualification branch is authorized",
        "original Codespace checkout must be Binilts03/Public",
        "controller authorization boundary changed",
    ):
        assert assertion in source
    for dangerous in (
        "gh codespace ports visibility", "git push", "git checkout",
        "remote_manage", "spawn_worker(", "run_worker(",
        "responses.create(", "openai.responses.", "chmod -R",
        "OPENAI_ADMIN_KEY=", "0.0.0.0:8770",
    ):
        assert dangerous not in source, dangerous


def test_validate_cli_offline_and_no_installs(capsys, monkeypatch):
    monkeypatch.setattr(m.sys, "argv", ["manage.py", "validate"])
    m.main()
    captured = capsys.readouterr().out
    assert "TUNNEL_NON_SECRET_PROFILE_VALID" in captured
    assert "NO_DOWNLOAD_NO_INSTALL_NO_MODEL_CALL" in captured



def test_install_is_independent_of_controller_and_worker_processes(tmp_path, monkeypatch):
    """Catch the real Codespaces regression: pgrep refused installation."""
    import inspect
    import pwd
    assert "pgrep" not in inspect.getsource(m.require_host)
    assert "require_live_services" not in inspect.getsource(m.cmd_install)
    assert "require_live_services" not in inspect.getsource(m.cmd_key)
    assert "require_live_services()" in inspect.getsource(m.cmd_client)

    monkeypatch.setattr(m, "BASE", tmp_path / "pinned")
    monkeypatch.setattr(m, "PRIVATE", tmp_path / "private")
    monkeypatch.setattr(m, "INSTALLED_PROFILE", m.BASE / "profile.yaml")
    monkeypatch.setattr(m, "BINARY", m.BASE / "tunnel-client")
    monkeypatch.setattr(m, "KEY_FILE", m.PRIVATE / "runtime.key")
    monkeypatch.setattr(m, "RUN_AS", pwd.getpwuid(__import__("os").getuid()).pw_name)
    monkeypatch.setattr(m, "require_host", lambda: None)
    monkeypatch.setattr(m, "ensure_separate_user", lambda: None)
    monkeypatch.setattr(m, "download_release", lambda: {
        name: name.encode("utf-8") for name in m.EXPECTED_FILES
    })
    monkeypatch.setattr(m.os, "chown", lambda *args: None)
    monkeypatch.setattr(
        m, "require_live_services",
        lambda: pytest.fail("offline installation unexpectedly needs running worker/controller"),
    )
    m.cmd_install()
    assert m.BINARY.is_file()
    assert m.INSTALLED_PROFILE.read_text(encoding="utf-8") == m.PROFILE_TEXT
    assert not m.KEY_FILE.exists()
    with pytest.raises(m.Refusal, match="install paths already exist"):
        m.cmd_install()


def test_live_service_checks_apply_only_to_tunnel_activation(monkeypatch):
    """Doctor/run must be blocked before reading/using credentials while offline."""
    monkeypatch.setattr(m, "require_host", lambda: None)
    monkeypatch.setattr(m, "installed_gate", lambda: None)
    monkeypatch.setattr(
        m, "require_live_services",
        lambda: (_ for _ in ()).throw(m.Refusal("controller is not running")),
    )
    monkeypatch.setattr(
        m, "private_file",
        lambda *args: pytest.fail("read key despite failed live preflight"),
    )
    for verb in ("doctor", "run"):
        with pytest.raises(m.Refusal, match="controller is not running"):
            m.cmd_client(verb)
