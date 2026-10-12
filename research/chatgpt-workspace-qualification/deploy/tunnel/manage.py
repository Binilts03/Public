#!/usr/bin/env python3
"""Public-only Codespaces Secure MCP Tunnel client (NO OpenAI model calls).

Commands: validate (offline); install (explicit root, download pinned release);
key (explicit root, TTY secret); doctor/run (explicit root, separate UID).
No command enrolls workers, edits Git, opens inbound ports, or changes controller.
"""
from __future__ import annotations

import getpass
import hashlib
import io
import os
from pathlib import Path
import platform
import pwd
import re
import socket
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / "profile.yaml"
BASE = Path("/opt/public-chatgpt-tunnel")
PRIVATE = Path("/srv/chatgpt-tunnel")
INSTALLED_PROFILE = BASE / "profile.yaml"
KEY_FILE = PRIVATE / "runtime.key"
BINARY = BASE / "tunnel-client"
RUN_AS = "chatgpt-tunnel"
WORKER = "chatgpt-worker"
CONTROLLER = "chatgpt-controller"
TUNNEL_ID = "tunnel_6acd09e0298481919ac84778501b0aef"
RELEASE = "v0.0.15"
ASSET = "tunnel-client-v0.0.15-linux-amd64.zip"
DIGEST = "8c836dc5d68d68b663d9a5c5b28ff9fa780d9f7a3fffb1c306880b8f32fab5f1"
RELEASE_URL = "https://github.com/openai/tunnel-client/releases/download/" + RELEASE + "/" + ASSET
MAX_ARCHIVE = 36_000_000  # release is ~28 MB; guard download amplification
MAX_MEMBER = 60_000_000
EXPECTED_FILES = {
    "tunnel-client", "cloudflared", "cloudflared-manifest.json",
    "LICENSE", "NOTICE",
    "tunnel-client-v0.0.15-linux-amd64-licenses.txt",
    "tunnel-client-v0.0.15-linux-amd64.spdx.json",
}
PROFILE_TEXT = """# Based on openai/tunnel-client v0.0.15 sample_mcp_with_dcr.
# Non-secret, pinned qualification profile. NEVER add a runtime key here.
config_version: 1
control_plane:
  base_url: "https://api.openai.com"
  tunnel_id: "tunnel_6acd09e0298481919ac84778501b0aef"
  api_key: "env:CONTROL_PLANE_API_KEY"
health:
  listen_addr: "127.0.0.1:8770"
admin_ui:
  open_browser: false
log:
  level: info
  format: json
mcp:
  server_urls:
    - channel: main
      url: "http://127.0.0.1:8765/mcp"
"""


class Refusal(Exception):
    pass


def require(ok: bool, msg: str) -> None:
    if not ok:
        raise Refusal(msg)


def validate_profile(text: str) -> None:
    require(text == PROFILE_TEXT, "tunnel profile deviates from pinned OAuth/loopback contract")
    require("api_key: \"env:CONTROL_PLANE_API_KEY\"" in text,
            "tunnel runtime key must be an environment reference")


def private_file(path: Path, owner: str, mode: int) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    st = path.stat()
    return st.st_uid == pwd.getpwnam(owner).pw_uid and stat.S_IMODE(st.st_mode) == mode


def run_silent(args: list[str], *, timeout: int = 10) -> bool:
    return subprocess.run(
        args, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=False, timeout=timeout,
    ).returncode == 0


def require_host() -> None:
    require(platform.system() == "Linux" and platform.machine() == "x86_64",
            "only pinned Linux amd64 artifact supported")
    require(os.geteuid() == 0 and os.environ.get("SUDO_USER") == "codespace",
            "run as sudo from Codespaces 'codespace' owner")
    workspace = Path("/workspaces/Public")
    require(workspace.is_dir() and not workspace.is_symlink(),
            "expected original Public Codespaces checkout absent")
    require(subprocess.check_output(
        ["/usr/bin/git", "-C", str(workspace), "branch", "--show-current"],
        stderr=subprocess.DEVNULL, timeout=8, text=True,
    ).strip() == "experiments/chatgpt-workspace-qualification",
            "only the Public qualification branch is authorized")
    require(subprocess.check_output(
        ["/usr/bin/git", "-C", str(workspace), "remote", "get-url", "origin"],
        stderr=subprocess.DEVNULL, timeout=8, text=True,
    ).strip().rstrip("/") in (
        "https://github.com/Binilts03/Public",
        "https://github.com/Binilts03/Public.git",
    ), "original Codespace checkout must be Binilts03/Public")
    evidence = Path("/opt/public-chatgpt-mcp/codespaces-isolation-qualified")
    require(evidence.is_file() and not evidence.is_symlink()
            and evidence.stat().st_uid == 0
            and stat.S_IMODE(evidence.stat().st_mode) == 0o600,
            "root-owned private controller/worker attestation missing")
    controller_config = Path("/srv/chatgpt-controller/controller.env")
    require(private_file(controller_config, CONTROLLER, 0o600),
            "controller OAuth config is not isolated")
    # Do not echo private configuration. Check only fixed mandatory boundaries.
    config_lines = set(controller_config.read_text(encoding="utf-8").splitlines())
    for required_line in (
        "LOCAL_SHELL_MCP_DISABLE_LOCAL=true",
        "LOCAL_SHELL_MCP_REMOTE_ENABLED=true",
        "LOCAL_SHELL_MCP_AUTH_MODE=oauth",
        "LOCAL_SHELL_MCP_AUTH_BYPASS_LOCALHOST=false",
    ):
        require(required_line in config_lines, "controller authorization boundary changed")
    require(run_silent(["/usr/sbin/runuser", "-u", WORKER, "--", "test", "!", "-x", "/workspaces"]),
            "worker access to original workspace is unsafe")
    require(run_silent(["/usr/sbin/runuser", "-u", WORKER, "--", "test", "!", "-r",
                        "/srv/chatgpt-controller/controller.env"]),
            "worker can read controller secrets")
    require(run_silent(["pgrep", "-u", CONTROLLER, "-f", "nondumpable_mcp_entrypoint.py"]),
            "controller is not running")
    require(run_silent(["pgrep", "-u", WORKER, "-f", "local_shell_mcp.remote_worker"]),
            "existing registered worker is not running; do not re-enroll")


def read_release_zip(data: bytes) -> dict[str, bytes]:
    require(hashlib.sha256(data).hexdigest() == DIGEST,
            "download does not match pinned upstream release digest")
    result: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        require({x.filename for x in members} == EXPECTED_FILES,
                "upstream release asset member list changed")
        for item in members:
            kind = (item.external_attr >> 16) & 0o170000
            require(kind in (0, stat.S_IFREG), "release contains nonregular file")
            require(not item.is_dir() and item.file_size <= MAX_MEMBER,
                    "release contains directory or oversized file")
            result[item.filename] = archive.read(item)
    require(result["tunnel-client"] and result["cloudflared"],
            "upstream release executable missing")
    return result


def download_release() -> dict[str, bytes]:
    request = urllib.request.Request(RELEASE_URL, headers={"User-Agent": "Public-tunnel-qualification/1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        require(response.status == 200, "pinned tunnel-client release download failed")
        buffer = response.read(MAX_ARCHIVE + 1)
        require(len(buffer) <= MAX_ARCHIVE, "tunnel-client download exceeds artifact limit")
    return read_release_zip(buffer)


def ensure_separate_user() -> None:
    try:
        user = pwd.getpwnam(RUN_AS)
    except KeyError:
        require(run_silent([
            "/usr/sbin/useradd", "--system", "--user-group", "--no-create-home",
            "--home-dir", str(PRIVATE), "--shell", "/usr/sbin/nologin", RUN_AS]),
            "could not create dedicated tunnel identity")
        user = pwd.getpwnam(RUN_AS)
    require(user.pw_uid not in (0, pwd.getpwnam(WORKER).pw_uid,
                                pwd.getpwnam(CONTROLLER).pw_uid),
            "tunnel user must have a separate non-root UID")
    group_info = subprocess.check_output(["/usr/bin/id", "-nG", RUN_AS], text=True).split()
    require(not (set(group_info) & {"sudo", "docker", "ssh", "codespace"}),
            "tunnel identity has unexpected privileged groups")
    require(user.pw_shell == "/usr/sbin/nologin", "tunnel identity shell unexpected")

    # Deny traversal through /workspaces without modifying any sibling directory.
    # -n prevents recomputing the ACL mask (which can accidentally broaden access).
    require(run_silent(["/usr/bin/setfacl", "-n", "-m", f"u:{RUN_AS}:---", "/workspaces"]),
            "unable to isolate tunnel user from Codespaces workspaces")
    require(run_silent(["/usr/sbin/runuser", "-u", RUN_AS, "--",
                        "test", "!", "-x", "/workspaces"]),
            "tunnel user can traverse /workspaces")
    require(run_silent(["/usr/sbin/runuser", "-u", WORKER, "--",
                        "test", "!", "-x", "/workspaces"]),
            "worker workspace isolation changed")
    require(run_silent(["/usr/sbin/runuser", "-u", RUN_AS, "--",
                        "test", "!", "-r", "/srv/chatgpt-controller/controller.env"]),
            "tunnel identity can read controller credentials")


def cmd_install() -> None:
    require_host()
    require(not BASE.exists() and not PRIVATE.exists(),
            "tunnel install paths already exist; do not overwrite or reset")
    # Verify exact asset *before* making host changes.
    archive = download_release()
    ensure_separate_user()
    tunnel = pwd.getpwnam(RUN_AS)
    BASE.mkdir(mode=0o755)
    PRIVATE.mkdir(mode=0o700)
    os.chown(PRIVATE, tunnel.pw_uid, tunnel.pw_gid)
    for name in EXPECTED_FILES:
        destination = BASE / name
        with destination.open("xb") as file:
            file.write(archive[name])
        destination.chmod(0o755 if name in {"tunnel-client", "cloudflared"} else 0o644)
    INSTALLED_PROFILE.write_text(PROFILE_TEXT, encoding="utf-8")
    INSTALLED_PROFILE.chmod(0o644)
    # No service is started; no external authentication or model invocation.
    print("TUNNEL_PINNED_RELEASE_INSTALLED_NO_DAEMON")
    print("TUNNEL_UID_ISOLATION_PASS")
    print("NO_KEY_NO_WORKER_ENROLLMENT_NO_PORT_CHANGES_NO_GIT_WRITES")


def installed_gate() -> None:
    require(BASE.is_dir() and not BASE.is_symlink(), "tunnel client not installed")
    require(BASE.stat().st_uid == 0, "tunnel install directory not root owned")
    require(BINARY.is_file() and not BINARY.is_symlink()
            and BINARY.stat().st_uid == 0
            and not (stat.S_IMODE(BINARY.stat().st_mode) & 0o022),
            "installed binary is absent or mutable by untrusted users")
    require(private_file(INSTALLED_PROFILE, "root", 0o644),
            "installed profile ownership or mode invalid")
    validate_profile(INSTALLED_PROFILE.read_text(encoding="utf-8"))
    require(PRIVATE.is_dir() and not PRIVATE.is_symlink()
            and PRIVATE.stat().st_uid == pwd.getpwnam(RUN_AS).pw_uid
            and stat.S_IMODE(PRIVATE.stat().st_mode) == 0o700,
            "private runtime directory permissions invalid")
    require(run_silent(["/usr/sbin/runuser", "-u", RUN_AS, "--",
                        "test", "!", "-x", "/workspaces"]),
            "tunnel identity can traverse original workspaces")


def cmd_key() -> None:
    require_host()
    installed_gate()
    require(not KEY_FILE.exists() and not KEY_FILE.is_symlink(),
            "existing runtime key present; never overwrite it implicitly")
    require(sys.stdin.isatty(), "enter runtime key interactively, not via piping/arguments")
    value = getpass.getpass("OpenAI tunnel runtime key (hidden): ")
    require(32 <= len(value) <= 512 and value.isascii()
            and not any(c.isspace() for c in value),
            "runtime key is empty or malformed")
    tunnel = pwd.getpwnam(RUN_AS)
    fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.fchown(fd, tunnel.pw_uid, tunnel.pw_gid)
        os.fchmod(fd, 0o600)
        os.write(fd, value.encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    print("TUNNEL_RUNTIME_KEY_STORED_PRIVATE_NO_KEY_ECHO")


def cmd_client(verb: str) -> None:
    require_host()
    installed_gate()
    require(private_file(KEY_FILE, RUN_AS, 0o600),
            "runtime key not provisioned or not private")
    key = KEY_FILE.read_text(encoding="ascii")
    require(32 <= len(key) <= 512 and not any(x.isspace() for x in key),
            "runtime key malformed")
    # Never pass credentials via argv, Git config, profile, or repo environment.
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(PRIVATE),
        "XDG_CONFIG_HOME": str(PRIVATE),
        "LANG": "C.UTF-8",
        "CONTROL_PLANE_API_KEY": key,
        "NO_PROXY": "127.0.0.1,localhost",
    }
    if verb == "run":
        # The health UI must remain local-only, and duplicate tunnel clients
        # must not compete for the same tunnel ID.
        with socket.socket() as s:
            s.settimeout(2)
            require(s.connect_ex(("127.0.0.1", 8770)) != 0,
                    "local tunnel health port already bound; refuse duplicate run")
    print("TUNNEL_" + verb.upper() + "_BEGIN (local client only; no model API invocation)", flush=True)
    args = ["/usr/sbin/runuser", "-u", RUN_AS, "--",
            str(BINARY), verb, "--profile-file", str(INSTALLED_PROFILE)]
    # Foreground: no unsupervised process; CTRL+C stops the client.
    # The vendor binary is responsible for redacting its own logs.
    result = subprocess.run(args, cwd=PRIVATE, env=env, check=False)
    require(result.returncode == 0, "tunnel client " + verb + " returned nonzero status")
    print("TUNNEL_" + verb.upper() + "_PASS")


def main() -> None:
    require(len(sys.argv) == 2, "usage: manage.py validate|install|key|doctor|run")
    verb = sys.argv[1]
    require(verb in {"validate", "install", "key", "doctor", "run"},
            "unsupported operation")
    validate_profile(PROFILE.read_text(encoding="utf-8"))
    if verb == "validate":
        print("TUNNEL_NON_SECRET_PROFILE_VALID: pinned v0.0.15; main channel; OAuth/DCR; loopback health")
        print("NO_DOWNLOAD_NO_INSTALL_NO_MODEL_CALL_NO_GIT_WRITES")
    elif verb == "install":
        cmd_install()
    elif verb == "key":
        cmd_key()
    else:
        cmd_client(verb)


if __name__ == "__main__":
    try:
        main()
    except (Refusal, OSError, ValueError, RuntimeError,
            subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        # No arbitrary errors or secret-bearing output. Reason only if ours.
        if isinstance(exc, Refusal):
            print("BLOCKED: " + str(exc), file=sys.stderr)
        else:
            print("BLOCKED: tunnel deployment error class=" + type(exc).__name__,
                  file=sys.stderr)
        raise SystemExit(2)
