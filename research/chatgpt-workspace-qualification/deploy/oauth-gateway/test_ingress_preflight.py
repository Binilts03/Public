"""No-network, no-live-account qualification for OAuth-only HTTPS ingress."""
from __future__ import annotations

import json
import re
import socket
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cloudflare_ingress as cf
import qualify_ingress as q
import gateway as g

ISSUER = "https://auth.example.com"
UUID = "b5b040e1-fdb1-4c15-8f37-cac3372b7e97"
RESOURCE = "https://api.openai.com/v1/mcp/tunnel_6acd09e0298481919ac84778501b0aef"


def response_for(path):
    if path == "/.well-known/oauth-authorization-server":
        return 200, {"Content-Type": "application/json"}, json.dumps({
            "issuer": ISSUER,
            "authorization_endpoint": ISSUER + "/oauth/authorize",
            "registration_endpoint": ISSUER + "/oauth/register",
            "token_endpoint": ISSUER + "/oauth/token",
            "code_challenge_methods_supported": ["S256"],
        }).encode()
    return 404, {"Content-Type": "application/json"}, b'{"error":"not_found"}'


def test_read_only_public_https_preflight_accepts_strict_oauth_only_edge():
    queried = []
    def mock_fetch(hostname, path):
        assert hostname == "auth.example.com"
        queried.append(path)
        return response_for(path)
    outcome = q.external_report(ISSUER, fetch=mock_fetch)
    assert "PUBLIC_INGRESS_READ_ONLY_PREFLIGHT_PASS" in outcome
    assert queried == ["/.well-known/oauth-authorization-server", *q.DENIED_PATHS]
    assert "/oauth/token" not in queried
    assert "/oauth/register" not in queried
    assert "/oauth/authorize" not in queried


@pytest.mark.parametrize("exposed, status, headers", [
    ("/mcp", 200, {}),
    ("/remote/poll", 401, {}),
    ("/ui", 403, {}),
    ("/mcp", 302, {"Location": "https://example.com/login"}),
    ("/healthz", 500, {}),
    ("/download/fixture", 200, {}),
])
def test_external_preflight_refuses_exposed_or_intercepted_non_oauth_routes(
    exposed, status, headers
):
    def mock_fetch(hostname, path):
        if path == exposed:
            return status, headers, b""
        return response_for(path)
    with pytest.raises(g.Refusal, match="exposed or redirected"):
        q.external_report(ISSUER, fetch=mock_fetch)


@pytest.mark.parametrize("bad", [
    "http://auth.example.com", "https://127.0.0.1",
    "https://198.51.100.24", "https://localhost", "https://auth.example.test",
    "https://auth.example.invalid", "https://auth.example.local",
    "https://auth.example.internal", "https://repo-8765.app.github.dev",
    "https://auth.example.com/oauth",
    "https://auth.example.com?redirect=https://x.example",
])
def test_public_hostname_validation_denies_private_test_or_pathful_inputs(bad):
    with pytest.raises((g.Refusal, ValueError)):
        q.validate_public_hostname(bad)


def test_local_preflight_is_read_only_and_detects_controller_migration_mismatch(monkeypatch):
    auth = {
        "issuer": "https://private-8765.app.github.dev",
        "code_challenge_methods_supported": ["S256"],
    }
    resource = {"resource": "https://private-8765.app.github.dev"}
    monkeypatch.setattr(
        q, "_local_get",
        lambda path, **kw: (200, b"{}")
    )
    monkeypatch.setattr(
        q, "request_upstream",
        lambda method, path, **kw: (
            200, {}, json.dumps(
                auth if path.endswith("oauth-authorization-server") else resource
            ).encode()
        )
    )
    class User:
        pass
    monkeypatch.setattr(q.pwd, "getpwnam", lambda name: User())
    outcome = q.local_report(controller_port=8765, health_port=8770,
                             gateway_port=0, expected_issuer=ISSUER,
                             expected_resource=RESOURCE)
    assert "CONTROLLER_MIGRATION_CONTRACT_MISMATCH_NO_WRITE" in outcome
    assert "CONTROLLER_ISSUER_CODESPACES_PRIVATE" in outcome
    assert "CONTROLLER_PKCE_S256_PASS" in outcome
    assert "NO_KEYS_READ_NO_MUTATION_NO_EXTERNAL_REQUESTS" in outcome
    assert all("sk-" not in line and "Bearer" not in line for line in outcome)


def test_local_preflight_reports_migration_match_after_private_config_update(monkeypatch):
    monkeypatch.setattr(q, "_local_get", lambda path, **kw: (200, b"{}"))
    monkeypatch.setattr(q, "request_upstream", lambda method, path, **kw: (
        200, {}, json.dumps(
            {"issuer": ISSUER, "code_challenge_methods_supported": ["S256"]}
            if path.endswith("oauth-authorization-server")
            else {"resource": RESOURCE}
        ).encode(),
    ))
    monkeypatch.setattr(q.pwd, "getpwnam", lambda name: (_ for _ in ()).throw(KeyError))
    outcome = q.local_report(gateway_port=0, expected_issuer=ISSUER,
                             expected_resource=RESOURCE)
    assert "CONTROLLER_MIGRATION_CONTRACT_MATCH" in outcome
    assert "GATEWAY_SERVICE_UID_NOT_STAGED" in outcome


def test_cf_named_tunnel_only_exact_oauth_paths_and_catchall_404():
    text = cf.render(ISSUER, UUID)
    cf.validate_structure(text, issuer=ISSUER, tunnel_uuid=UUID)
    assert f"tunnel: {UUID}" in text
    assert "service: http://127.0.0.1:8781" in text
    assert "httpHostHeader: auth.example.com" in text
    assert text.rstrip().endswith("- service: http_status:404")
    assert "8765" not in text and "8770" not in text and "/mcp" not in text
    assert "0.0.0.0" not in text and "noTLSVerify" not in text
    assert "service: http://" in text and text.count("service: http://") == 1
    allow = re.compile(cf.OAUTH_ONLY_PATH_REGEX)
    for path in g.ALLOWED:
        assert allow.fullmatch(path), path
    for path in q.DENIED_PATHS + (
        "/.well-known/oauth-protected-resource", "/oauth/token/extra",
        "/oauth/register/../mcp", "//oauth/token", "/oauth/authorizE",
        "/oauth/token.css",
    ):
        assert not allow.fullmatch(path), path


def test_cf_ingress_render_rejects_uncontrolled_credential_or_hostname():
    with pytest.raises(g.Refusal):
        cf.render("https://private-8765.app.github.dev", UUID)
    with pytest.raises(ValueError):
        cf.render(ISSUER, "tunnel_6acd09e0298481919ac84778501b0aef")
    with pytest.raises(g.Refusal):
        cf.validate_structure(
            cf.render(ISSUER, UUID).replace("http_status:404", "http://127.0.0.1:8765"),
            issuer=ISSUER, tunnel_uuid=UUID,
        )


def test_read_only_inspection_does_not_access_credentials_or_services():
    sources = [
        (HERE / "qualify_ingress.py").read_text(),
        (HERE / "cloudflare_ingress.py").read_text(),
    ]
    for src in sources:
        assert "subprocess.run" not in src
        assert "os.chmod(" not in src
        assert "os.chown(" not in src
        assert "git push" not in src
        assert "getpass" not in src
        assert "control_plane_api_key" not in src
        assert "controller.env" not in src
    assert 'http.client.HTTPSConnection(' in sources[0]
    assert "ssl.create_default_context()" in sources[0]
    assert "NO_KEYS_READ_NO_MUTATION_NO_EXTERNAL_REQUESTS" in sources[0]
