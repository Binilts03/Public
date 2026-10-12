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
    monkeypatch.setattr(m, "installed_gate", lambda: None)
    monkeypatch.setattr(
        m, "require_live_services",
        lambda: pytest.fail("offline installation unexpectedly needs running worker/controller"),
    )
    m.cmd_install()
    assert m.BINARY.is_file()
    assert m.INSTALLED_PROFILE.read_text(encoding="utf-8") == m.PROFILE_TEXT
    assert stat.S_IMODE(m.BASE.stat().st_mode) == 0o755
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



@pytest.fixture
def pristine_installed_tree(tmp_path, monkeypatch):
    """Disposable substitute; no real Codespaces filesystem or identity touched."""
    import os
    import pwd
    base = tmp_path / "install"
    private = tmp_path / "runtime"
    base.mkdir(mode=0o700)
    base.chmod(0o700)
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    for name in m.EXPECTED_FILES | {"profile.yaml"}:
        p = base / name
        p.write_text(m.PROFILE_TEXT if name == "profile.yaml" else "disposable-test-asset")
        p.chmod(0o755 if name in {"tunnel-client", "cloudflared"} else 0o644)
    monkeypatch.setattr(m, "BASE", base)
    monkeypatch.setattr(m, "PRIVATE", private)
    monkeypatch.setattr(m, "KEY_FILE", private / "runtime.key")
    uid = os.getuid()
    assert pwd.getpwuid(uid).pw_uid == uid
    return base, private, uid


def test_stage_repair_is_pristine_only_and_no_file_is_mutated(pristine_installed_tree):
    import os
    base, private, uid = pristine_installed_tree
    prior = {name: (base / name).read_bytes() for name in m.EXPECTED_FILES | {"profile.yaml"}}
    assert m.verify_pristine_install(root_uid=uid, tunnel_uid=uid) == 0o700
    m.repair_verified_directory(owner_uid=uid)
    assert stat.S_IMODE(base.stat().st_mode) == 0o755
    assert m.verify_pristine_install(root_uid=uid, tunnel_uid=uid) == 0o755
    assert {name: (base / name).read_bytes() for name in prior} == prior
    assert list(private.iterdir()) == []
    with pytest.raises(m.Refusal, match="changed before repair"):
        m.repair_verified_directory(owner_uid=uid)


def test_stage_repair_refuses_unexpected_files_secrets_symlinks_and_modes(pristine_installed_tree):
    base, private, uid = pristine_installed_tree
    original = base / "profile.yaml"
    original.write_text("malicious-profile")
    with pytest.raises(m.Refusal, match="profile differs"):
        m.verify_pristine_install(root_uid=uid, tunnel_uid=uid)
    original.write_text(m.PROFILE_TEXT)
    (base / "intruder").write_text("unknown")
    with pytest.raises(m.Refusal, match="unexpected files"):
        m.verify_pristine_install(root_uid=uid, tunnel_uid=uid)
    (base / "intruder").unlink()
    original.unlink()
    original.symlink_to(private / "runtime.key")
    with pytest.raises(m.Refusal, match="ownership, kind or mode"):
        m.verify_pristine_install(root_uid=uid, tunnel_uid=uid)
    original.unlink()
    original.write_text(m.PROFILE_TEXT)
    original.chmod(0o644)
    binary = base / "tunnel-client"
    binary.chmod(0o777)
    with pytest.raises(m.Refusal, match="ownership, kind or mode"):
        m.verify_pristine_install(root_uid=uid, tunnel_uid=uid)
    binary.chmod(0o755)
    (private / "runtime.key").write_text("fake-fixture-secret")
    with pytest.raises(m.Refusal, match="not pristine"):
        m.verify_pristine_install(root_uid=uid, tunnel_uid=uid)


def test_install_mode_ignores_restrictive_umask(tmp_path, monkeypatch):
    import os
    import pwd
    owner = pwd.getpwuid(os.getuid()).pw_name
    monkeypatch.setattr(m, "BASE", tmp_path / "bundle")
    monkeypatch.setattr(m, "PRIVATE", tmp_path / "private")
    monkeypatch.setattr(m, "INSTALLED_PROFILE", m.BASE / "profile.yaml")
    monkeypatch.setattr(m, "BINARY", m.BASE / "tunnel-client")
    monkeypatch.setattr(m, "KEY_FILE", m.PRIVATE / "runtime.key")
    monkeypatch.setattr(m, "RUN_AS", owner)
    monkeypatch.setattr(m, "require_host", lambda: None)
    monkeypatch.setattr(m, "ensure_separate_user", lambda: None)
    monkeypatch.setattr(m, "download_release", lambda: {
        name: name.encode("ascii") for name in m.EXPECTED_FILES
    })
    monkeypatch.setattr(m.os, "chown", lambda *args: None)
    monkeypatch.setattr(m, "installed_gate", lambda: None)
    old_umask = os.umask(0o077)
    try:
        m.cmd_install()
    finally:
        os.umask(old_umask)
    assert stat.S_IMODE(m.BASE.stat().st_mode) == 0o755
    assert stat.S_IMODE(m.PRIVATE.stat().st_mode) == 0o700
    assert stat.S_IMODE(m.INSTALLED_PROFILE.stat().st_mode) == 0o644
    assert stat.S_IMODE(m.BINARY.stat().st_mode) == 0o755



def test_codespaces_root_setgid_directory_is_accepted_without_repair(pristine_installed_tree):
    """Reproduces live root:oryx 2755 with safe non-writable group bits."""
    base, private, uid = pristine_installed_tree
    base.chmod(0o2755)
    assert stat.S_IMODE(base.stat().st_mode) == 0o2755
    assert m.acceptable_root_install_mode(stat.S_IMODE(base.stat().st_mode))
    assert m.verify_pristine_install(root_uid=uid, tunnel_uid=uid) == 0o2755
    with pytest.raises(m.Refusal, match="changed before repair"):
        m.repair_verified_directory(owner_uid=uid)
    assert stat.S_IMODE(base.stat().st_mode) == 0o2755
    assert list(private.iterdir()) == []


@pytest.mark.parametrize(
    "mode,allowed", [
        (0o755, True), (0o2755, True),
        (0o700, False), (0o2700, False),
        (0o775, False), (0o2775, False),
        (0o1775, False), (0o4755, False),
        (0o3755, False), (0o2777, False),
    ],
)
def test_root_install_mode_allowlist_denies_unexpected_bits(mode, allowed):
    assert m.acceptable_root_install_mode(mode) is allowed


@pytest.mark.parametrize("unsafe_mode", [0o775, 0o2775, 0o1775, 0o4755])
def test_pristine_inspection_rejects_unsafe_special_modes(pristine_installed_tree, unsafe_mode):
    base, _, uid = pristine_installed_tree
    base.chmod(unsafe_mode)
    with pytest.raises(m.Refusal, match="not an expected root-owned"):
        m.verify_pristine_install(root_uid=uid, tunnel_uid=uid)
