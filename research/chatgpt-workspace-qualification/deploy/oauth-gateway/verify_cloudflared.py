#!/usr/bin/env python3
"""Ephemeral CI verification against pinned cloudflared bundled by OpenAI.

Only a verified ZIP release is downloaded. Executes cloudflared ingress
validation and match rules locally; no Cloudflare API login, DNS, tunnel
creation, public endpoint, live Codespace, or credentials are accessed.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import urlopen
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cloudflare_ingress import render

# Identical to deploy/tunnel/manage.py. The ZIP checksum gates executable bytes.
RELEASE = "v0.0.15"
URL = ("https://github.com/openai/tunnel-client/releases/download/"
       "v0.0.15/tunnel-client-v0.0.15-linux-amd64.zip")
SHA256 = "8c836dc5d68d68b663d9a5c5b28ff9fa780d9f7a3fffb1c306880b8f32fab5f1"
MAX_DOWNLOAD = 36_000_000
MAX_BINARY = 65_000_000

ISSUER = "https://auth.example.com"
TEST_UUID = "b5b040e1-fdb1-4c15-8f37-cac3372b7e97"


def must(condition, description):
    if not condition:
        raise RuntimeError("pinned vendor ingress test: " + description)


def run_tool(executable: Path, config: Path, *args: str):
    proc = subprocess.run(
        [str(executable), "--config", str(config), "tunnel", "ingress", *args],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        check=False, timeout=20, text=True, stdin=subprocess.DEVNULL,
    )
    must(proc.returncode == 0, "cloudflared ingress command failed")
    return proc.stdout


def main() -> None:
    with urlopen(URL, timeout=35) as reply:
        data = reply.read(MAX_DOWNLOAD + 1)
    must(len(data) <= MAX_DOWNLOAD, "release exceeds pinned maximum")
    must(hashlib.sha256(data).hexdigest() == SHA256, "release SHA256 differs")
    with tempfile.TemporaryDirectory(prefix="public-cf-ingress-ci-") as name:
        root = Path(name)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entry = archive.getinfo("cloudflared")
            must(entry.file_size <= MAX_BINARY, "binary exceeds pinned maximum")
            binary = root / "cloudflared"
            binary.write_bytes(archive.read(entry))
            binary.chmod(0o700)
        config = root / "ingress.yml"
        config.write_text(render(ISSUER, TEST_UUID), encoding="utf-8")
        run_tool(binary, config, "validate")
        for path in (
            "/oauth/register", "/oauth/authorize", "/oauth/token",
            "/.well-known/oauth-authorization-server",
            "/.well-known/openid-configuration",
        ):
            out = run_tool(binary, config, "rule", ISSUER + path)
            must("Matched rule #0" in out and "127.0.0.1:8781" in out,
                 "OAuth route did not resolve to gateway: " + path)
        for path in (
            "/mcp", "/remote/register", "/remote/poll", "/readyz",
            "/ui", "/download/test", "/", "/oauth/token-other",
        ):
            out = run_tool(binary, config, "rule", ISSUER + path)
            must("Matched rule #1" in out and "http_status:404" in out,
                 "non-OAuth route did not match default deny: " + path)
        # Wrong hostname must not reach the OAuth gateway even on an allowed path.
        out = run_tool(binary, config, "rule", "https://attacker.example/oauth/authorize")
        must("Matched rule #1" in out and "http_status:404" in out,
             "unapproved hostname was routed to gateway")
    print("PINNED_CLOUDFLARED_OAUTH_PATH_AND_HOSTNAME_ALLOWLIST_PASS")
    print("DEFAULT_DENY_404_PASS_NO_PUBLIC_INGRESS_NO_CREDENTIALS_NO_SERVICE_CHANGES")


if __name__ == "__main__":
    main()
