#!/usr/bin/env python3
"""Read-only Codespaces MCP controller startup diagnosis.

Prints no OAuth settings, secrets, credentials, or raw untrusted log text.
Does not modify processes, filesystem permissions or public port settings.
Run with sudo python3 <path>. The caller must review the tool before running.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import os
import re
import socket
import subprocess
import sys

CONTROLLER = "chatgpt-controller"
WORKER = "chatgpt-worker"
LOG = Path("/srv/chatgpt-controller/logs/controller.log")
ROOT = Path("/srv/chatgpt-controller")
RUNTIME = Path("/opt/public-chatgpt-mcp")
ENV_PATH = ROOT / "controller.env"

def probe(label: str, argv: list[str]) -> bool:
    try:
        p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           check=False, text=True, timeout=5)
        print(f"{label}: {'PASS' if p.returncode == 0 else 'NO'}")
        return p.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        print(f"{label}: ERROR")
        return False

def http_code(path: str) -> str:
    try:
        from urllib.error import HTTPError, URLError
        from urllib.request import Request, urlopen
        req = Request("http://127.0.0.1:8765" + path, method="GET")
        with urlopen(req, timeout=3) as response:
            return str(response.status)
    except HTTPError as e:
        return str(e.code)
    except (URLError, TimeoutError, OSError):
        return "NO_RESPONSE"

def describe_log() -> None:
    if not LOG.is_file():
        print("private_log: MISSING")
        return
    data = LOG.read_bytes()
    print(f"private_log: PRESENT bytes={len(data)}")
    # Only emit fixed, predefined reason labels. NEVER output log substrings.
    text = data.decode("utf-8", errors="replace").lower()[-500_000:]
    hints = {
        "invalid_runtime_import": "modulenotfounderror",
        "permission_denied": "permissionerror",
        "missing_file": "filenotfounderror",
        "os_error": "oserror",
        "oauth_validation_error": "local_shell_mcp_oauth_jwt_secret must",
        "oauth_pin_validation_error": "local_shell_mcp_oauth_admin_pin must",
        "bad_cli_arguments": "unrecognized arguments",
        "runtime_error": "runtimeerror",
        "python_traceback": "traceback (most recent call last)",
        "socket_bind_error": "address already in use",
        "read_only_fs": "read-only file system",
        "cannot_create_path": "failed to create",
        "invalid_settings": "validationerror",
        "startup_failed": "application startup failed",
        "server_started": "uvicorn running on",
    }
    hits = [name for name, needle in hints.items() if needle in text]
    print("log_diagnostic_categories:", ",".join(hits) if hits else "UNKNOWN")
    # Disclose the exception class only, not its potentially secret-bearing message.
    exceptions = re.findall(
        r"(?m)^(?:[a-zA-Z_][a-zA-Z0-9_.]*\.)?([a-zA-Z_][a-zA-Z0-9_]*(?:Error|Exception)):", text,
    )
    if exceptions:
        print("exception_classes:", ",".join(sorted(set(exceptions))[:12]))

def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Run as root through sudo; no secrets are printed")
    print("CODESPACES_CONTROLLER_DIAG_V1 read-only; secrets and raw logs suppressed")
    print("python:", sys.version.split()[0])
    for name, path in [
        ("controller_env", ENV_PATH),
        ("controller_log", LOG),
        ("runtime_python", RUNTIME / "venv/bin/python"),
        ("runtime_entrypoint", RUNTIME / "nondumpable_mcp_entrypoint.py"),
        ("controller_state", ROOT / "state"),
        ("controller_empty", ROOT / "empty"),
    ]:
        try:
            info = path.stat()
            print(f"{name}: {'PRESENT' if path.exists() else 'MISSING'} "
                  f"uid={info.st_uid} mode={info.st_mode & 0o777:03o}")
        except OSError:
            print(f"{name}: MISSING")
    probe("controller_identity", ["id", CONTROLLER])
    probe("worker_identity", ["id", WORKER])
    probe("controller_process", ["pgrep", "-u", CONTROLLER, "-f", "nondumpable_mcp_entrypoint.py"])
    probe("controller_python_import", ["runuser", "-u", CONTROLLER, "--",
                                      str(RUNTIME / "venv/bin/python"),
                                      "-c", "import local_shell_mcp"])
    print("loopback_healthz:", http_code("/healthz"))
    print("loopback_oauth_metadata:", http_code("/.well-known/oauth-authorization-server"))
    describe_log()
    print("NO_MUTATIONS_NO_SECRETS_NO_PUBLIC_INGRESS")

if __name__ == "__main__":
    main()
