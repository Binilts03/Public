#!/usr/bin/env python3
"""Actual pinned local-shell-mcp OAuth via gateway + private MCP token acceptance.

Ephemeral loopback ports and temp workspace only. DOES NOT deploy HTTPS or
touch the user's Codespace controller, registered worker, or installed key.
"""
from __future__ import annotations

import asyncio
import hashlib
import base64
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from real_process_oauth_e2e import port_available, server  # noqa: E402
import gateway as g  # noqa: E402

ISSUER = "https://auth.example.test"
RESOURCE = "https://api.openai.com/v1/tunnel/tunnel_6acd09e0298481919ac84778501b0aef/mcp"
CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"


async def mcp_authenticated_initialize(url: str, token: str) -> None:
    async with httpx.AsyncClient(
        headers={"Authorization": "Bearer " + token}, timeout=30,
    ) as transport:
        async with streamable_http_client(url + "/mcp", http_client=transport) as streams:
            async with ClientSession(streams[0], streams[1]) as client:
                info = await client.initialize()
                assert info.serverInfo.name
                tools = await client.list_tools()
                names = {item.name for item in tools.tools}
                assert "remote_manage" not in names or len(names) > 1
                assert len(names) >= 3


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="public-oauth-gateway-real-") as directory:
        temp = Path(directory)
        workspace = temp / "fixture-workspace"
        workspace.mkdir()
        unrelated = temp / "unrelated.txt"
        unrelated.write_text("UNCHANGED\n")
        upstream_port = port_available()
        private_url = f"http://127.0.0.1:{upstream_port}"
        admin_pin = secrets.token_urlsafe(40)
        signing_secret = secrets.token_hex(40)
        env = {
            **os.environ,
            "LOCAL_SHELL_MCP_HOST": "127.0.0.1",
            "LOCAL_SHELL_MCP_PORT": str(upstream_port),
            "LOCAL_SHELL_MCP_MODE": "mcp",
            "LOCAL_SHELL_MCP_AUTH_MODE": "oauth",
            "LOCAL_SHELL_MCP_AUTH_BYPASS_LOCALHOST": "false",
            "LOCAL_SHELL_MCP_OAUTH_ADMIN_PIN": admin_pin,
            "LOCAL_SHELL_MCP_OAUTH_JWT_SECRET": signing_secret,
            "LOCAL_SHELL_MCP_OAUTH_ACCESS_TOKEN_TTL_S": "3600",
            "LOCAL_SHELL_MCP_OAUTH_ISSUER": ISSUER,
            "LOCAL_SHELL_MCP_OAUTH_RESOURCE": RESOURCE,
            "LOCAL_SHELL_MCP_PUBLIC_BASE_URL": ISSUER,
            "LOCAL_SHELL_MCP_WORKSPACE_ROOT": str(workspace),
            "LOCAL_SHELL_MCP_STATE_DIR": str(temp / "state"),
            "LOCAL_SHELL_MCP_REMOTE_ENABLED": "false",
            "LOCAL_SHELL_MCP_DISABLE_LOCAL": "true",
            "LOCAL_SHELL_MCP_UI_ENABLED": "false",
            "LOCAL_SHELL_MCP_LIVE_WORKSPACE_ENABLED": "false",
            "LOCAL_SHELL_MCP_ALLOW_FULL_CONTAINER": "false",
        }
        log = temp / "controller-private.log"
        with server(env, private_url, log):
            contract = g.Contract(ISSUER, RESOURCE, (CALLBACK,))
            g.check_controller_contract(contract, port=upstream_port)
            gateway = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                g.make_handler(contract, upstream_port=upstream_port),
            )
            thread = threading.Thread(target=gateway.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{gateway.server_port}"
                with httpx.Client(
                    base_url=url, headers={"Host": "auth.example.test"},
                    follow_redirects=False, timeout=10,
                ) as client:
                    meta = client.get("/.well-known/oauth-authorization-server")
                    assert meta.status_code == 200
                    assert meta.json()["issuer"] == ISSUER
                    assert client.get("/mcp").status_code == 404
                    assert client.get("/remote/poll").status_code == 404
                    assert client.get("/ui").status_code == 404
                    dcr = client.post("/oauth/register", json={
                        "client_name": "public-oauth-gateway-ci",
                        "redirect_uris": [CALLBACK],
                        "token_endpoint_auth_method": "none",
                    })
                    assert dcr.status_code in (200, 201), (dcr.status_code, dcr.text[:300])
                    client_id = dcr.json()["client_id"]
                    verifier = secrets.token_urlsafe(60)
                    challenge = base64.urlsafe_b64encode(
                        hashlib.sha256(verifier.encode()).digest()
                    ).decode().rstrip("=")
                    params = {
                        "response_type": "code", "client_id": client_id,
                        "redirect_uri": CALLBACK, "code_challenge": challenge,
                        "code_challenge_method": "S256",
                        "state": secrets.token_urlsafe(20),
                        "resource": RESOURCE,
                    }
                    consent = client.get("/oauth/authorize", params=params)
                    assert consent.status_code == 200, (consent.status_code, consent.text[:300])
                    assert b'name="pin"' in consent.content
                    approval = client.post("/oauth/authorize", data={**params, "pin": admin_pin})
                    assert approval.status_code == 302, (approval.status_code, approval.text[:300])
                    callback = urlsplit(approval.headers["location"])
                    assert callback.scheme == "https" and callback.netloc == "chatgpt.com"
                    query = parse_qs(callback.query)
                    assert query["iss"] == [ISSUER] and query["state"] == [params["state"]]
                    code = query["code"][0]
                    token_request = {
                        "grant_type": "authorization_code", "client_id": client_id,
                        "code": code, "redirect_uri": CALLBACK,
                    }
                    rejected = client.post("/oauth/token", data={
                        **token_request, "code_verifier": "X" * 43,
                    })
                    assert rejected.status_code == 400, "wrong PKCE was accepted"
                    issued = client.post("/oauth/token", data={
                        **token_request, "code_verifier": verifier,
                    })
                    assert issued.status_code == 200, (issued.status_code, issued.text[:300])
                    token = issued.json()["access_token"]
                    claims = jwt.decode(token, signing_secret, algorithms=["HS256"],
                                        audience=RESOURCE, issuer=ISSUER)
                    assert claims["client_id"] == client_id
                    assert claims["exp"] > claims["iat"]
                    replay = client.post("/oauth/token", data={
                        **token_request, "code_verifier": verifier,
                    })
                    assert replay.status_code == 400, "authorization code replay accepted"
                    bypass = httpx.post(private_url + "/mcp", json={
                        "jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2025-06-18",
                                   "capabilities": {}, "clientInfo": {
                                       "name": "negative", "version": "1",
                                   }},
                    }, headers={"Content-Type": "application/json",
                                "Accept": "application/json, text/event-stream"},
                        timeout=10)
                    assert bypass.status_code == 401, "private MCP allowed no token"
                asyncio.run(mcp_authenticated_initialize(private_url, token))
            finally:
                gateway.shutdown()
                gateway.server_close()
                thread.join(timeout=3)
        assert unrelated.read_text() == "UNCHANGED\n"
        print("REAL_PINNED_OAUTH_GATEWAY_E2E_PASS")
        print("DCR_PKCE_S256_ADMIN_PIN_ISSUER_AUDIENCE_TOKEN_REPLAY_MCP_INIT_PASS")
        print("GATEWAY_MCP_REMOTE_UI_DENIAL_PASS")
        print("NO_EXTERNAL_TLS_NO_LIVE_DEPLOYMENT_NO_GIT_OR_WORKER_CHANGES")


if __name__ == "__main__":
    main()
