#!/usr/bin/env python3
"""Validate a restricted local-shell-mcp profile and OAuth MCP ingress in-process.

Only ephemeral fixtures, generated test secrets and TestClient. This DOES NOT
verify external TLS, ChatGPT app installation or an actual browser OAuth callback.
"""
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
from fastapi.testclient import TestClient


def load_profile(path):
    settings = {}
    for raw in path.read_text().splitlines():
        line=raw.strip()
        if not line or line.startswith("#"):continue
        key, sep, value = line.partition("=")
        assert sep and key.startswith("LOCAL_SHELL_MCP_"), f"Invalid env assignment: {line}"
        assert key not in settings, f"Duplicate key {key}"
        settings[key]=value
    return settings


def main():
    profile=Path(sys.argv[1])
    values=load_profile(profile)
    with tempfile.TemporaryDirectory(prefix="public-oauth-profile-") as d:
        root=Path(d)
        fixture=root/"public"
        fixture.mkdir()
        values.update({
          "LOCAL_SHELL_MCP_WORKSPACE_ROOT":str(fixture),
          "LOCAL_SHELL_MCP_STATE_DIR":str(root/"state"),
          "LOCAL_SHELL_MCP_AGENT_CONFIG_DIR":str(root/"skills"),
          "LOCAL_SHELL_MCP_PUBLIC_BASE_URL":"https://workspace-test.example.invalid",
          "LOCAL_SHELL_MCP_OAUTH_ADMIN_PIN":secrets.token_urlsafe(32),
          "LOCAL_SHELL_MCP_OAUTH_JWT_SECRET":secrets.token_hex(32),
        })
        os.environ.update(values)
        from local_shell_mcp.settings import get_settings,validate_public_oauth_configuration
        get_settings.cache_clear()
        settings=get_settings()
        assert str(settings.workspace_root)==str(fixture)
        for name,value in {
            "host":"127.0.0.1","auth_mode":"oauth","auth_bypass_localhost":False,
            "require_auth_for_mcp_discovery":True,"remote_enabled":False,
            "allow_full_container":False,"ui_enabled":False,"live_workspace_enabled":False,
            "state_backend":"file","max_concurrent_commands":2,"oauth_access_token_ttl_s":86400
        }.items():
            actual=getattr(settings,name)
            assert actual==value,f"Profile field {name}: {actual!r}, required {value!r}"
        validate_public_oauth_configuration(settings)

        from local_shell_mcp.main import _build_mcp_http_app
        from local_shell_mcp.tools import build_mcp
        app=_build_mcp_http_app(build_mcp())
        payload={"jsonrpc":"2.0","id":1,"method":"initialize",
                 "params":{"protocolVersion":"2025-06-18","capabilities":{},
                           "clientInfo":{"name":"independent-oauth-gate","version":"1"}}}
        headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream",
                 "MCP-Protocol-Version":"2025-06-18"}
        with TestClient(app, base_url="https://workspace-test.example.invalid") as client:
            metadata=client.get("/.well-known/oauth-authorization-server")
            assert metadata.status_code==200,(metadata.status_code,metadata.text[:400])
            meta=metadata.json()
            assert meta.get("issuer")=="https://workspace-test.example.invalid",meta
            assert "S256" in meta.get("code_challenge_methods_supported",[]),meta
            protected=client.get("/.well-known/oauth-protected-resource")
            assert protected.status_code==200,(protected.status_code,protected.text[:400])
            denied=client.post("/mcp",json=payload,headers=headers)
            assert denied.status_code==401,(denied.status_code,denied.text[:600])
            bad=client.post("/mcp",json=payload,headers={**headers,"Authorization":"Bearer wrong-token"})
            assert bad.status_code==401,(bad.status_code,bad.text[:600])
            from local_shell_mcp.oauth import ALL_OAUTH_SCOPES,issue_access_token
            token=issue_access_token(client_id="fixture-client",
                scope=" ".join(ALL_OAUTH_SCOPES),resource="https://workspace-test.example.invalid")
            allowed=client.post("/mcp",json=payload,headers={**headers,"Authorization":"Bearer "+token})
            assert allowed.status_code in (200,202),(allowed.status_code,allowed.text[:900])
            assert "initialize" in allowed.text or "serverInfo" in allowed.text or "protocolVersion" in allowed.text,allowed.text[:900]
        gates=[
          "Restricted settings enforce no remote workers and no full-container access",
          "OAuth metadata with S256 PKCE",
          "Protected resource metadata",
          "Missing bearer rejected by MCP HTTP",
          "Invalid bearer rejected by MCP HTTP",
          "Issued short-lived test token can initialize MCP",
        ]
        report={"schema":"public-oauth-gate/v1","result":"PASS","checks":gates,
                "warning":"In-process TestClient, synthetic JWT. NOT a full OAuth authorization-code/PCKE browser flow, public TLS, actual ChatGPT plugin or OS sandbox."}
        Path("/tmp/candidate-fwerkor-oauth.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2))

if __name__=="__main__":main()
