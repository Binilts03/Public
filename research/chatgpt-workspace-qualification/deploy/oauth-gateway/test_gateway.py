"""Real HTTP tests against disposable loopback gateway and fake OAuth controller.

No GitHub account, Codespace service, worker, OpenAI key, public port or real
PIN is accessed. Tests cover actual socket routing and fail-closed responses.
"""
from __future__ import annotations

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import threading
from urllib.parse import urlencode

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("public_oauth_gateway", HERE / "gateway.py")
assert spec and spec.loader
g = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = g
spec.loader.exec_module(g)

ISSUER = "https://auth.example.test"
RESOURCE = "https://api.openai.com/v1/tunnel/tunnel_6acd09e0298481919ac84778501b0aef/mcp"
CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"
CONTRACT = g.Contract(ISSUER, RESOURCE, (CALLBACK,))


class FakeController(BaseHTTPRequestHandler):
    seen = []
    mismatch = False

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, obj, media="application/json", location=None):
        content = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Content-Type", media)
        if location:
            self.send_header("Location", location)
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        self.seen.append(("GET", self.path))
        if self.path == "/.well-known/oauth-authorization-server":
            self._send(200, {
                "issuer": "https://wrong.example" if self.mismatch else ISSUER,
                "authorization_endpoint": ISSUER + "/oauth/authorize",
                "token_endpoint": ISSUER + "/oauth/token",
                "registration_endpoint": ISSUER + "/oauth/register",
                "code_challenge_methods_supported": ["S256"],
            })
        elif self.path == "/.well-known/oauth-protected-resource":
            self._send(200, {"resource": RESOURCE, "authorization_servers": [ISSUER]})
        elif self.path.startswith("/oauth/authorize?"):
            self._send(200, b'<form method="post"></form>', "text/html; charset=utf-8")
        else:
            self._send(404, {"error": "not-found"})

    def do_POST(self):
        self.seen.append(("POST", self.path))
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/oauth/register":
            self._send(201, {"client_id": "fixture-123"})
        elif self.path == "/oauth/token":
            self._send(200, {"access_token": "fixture-only-token"})
        elif self.path == "/oauth/authorize":
            fields = g.unique_form(body.decode())
            callback = fields.get("redirect_uri", CALLBACK)
            if "evil" in fields:
                callback = "https://attacker.example/callback"
            location = callback + "?" + urlencode({"code": "fixture-code", "iss": ISSUER})
            self._send(302, b"", "text/html", location)
        else:
            self._send(404, {"error": "not-found"})


@pytest.fixture
def active_servers():
    FakeController.seen = []
    FakeController.mismatch = False
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeController)
    t1 = threading.Thread(target=upstream.serve_forever, daemon=True)
    t1.start()
    try:
        g.check_controller_contract(CONTRACT, port=upstream.server_port)
        gateway = g.BoundedLoopbackServer(
            ("127.0.0.1", 0), g.make_handler(CONTRACT, upstream_port=upstream.server_port)
        )
        t2 = threading.Thread(target=gateway.serve_forever, daemon=True)
        t2.start()
        try:
            yield gateway.server_port, FakeController.seen
        finally:
            gateway.shutdown()
            gateway.server_close()
            t2.join(timeout=2)
    finally:
        upstream.shutdown()
        upstream.server_close()
        t1.join(timeout=2)


def call(port, method, path, body=None, *, host=ISSUER.removeprefix("https://"),
         media=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        h = {"Host": host}
        if media:
            h["Content-Type"] = media
        if headers:
            h.update(headers)
        conn.request(method, path, body=body, headers=h)
        response = conn.getresponse()
        content = response.read()
        return response.status, dict(response.getheaders()), content
    finally:
        conn.close()


def auth_params():
    return {
        "response_type": "code", "client_id": "fixture-123",
        "redirect_uri": CALLBACK, "code_challenge_method": "S256",
        "code_challenge": "A" * 43, "resource": RESOURCE,
        "state": "opaque-fixture",
    }


def test_end_to_end_oauth_only_routes(active_servers):
    port, seen = active_servers
    status, headers, data = call(port, "GET", "/.well-known/oauth-authorization-server")
    assert status == 200 and json.loads(data)["issuer"] == ISSUER
    url = "/oauth/authorize?" + urlencode(auth_params())
    status, headers, html = call(port, "GET", url)
    assert status == 200 and b"<form" in html
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"
    status, _, payload = call(
        port, "POST", "/oauth/register",
        json.dumps({"redirect_uris": [CALLBACK], "token_endpoint_auth_method": "none"}),
        media="application/json",
    )
    assert status == 201 and json.loads(payload)["client_id"] == "fixture-123"
    status, headers, data = call(
        port, "POST", "/oauth/authorize",
        urlencode({**auth_params(), "pin": "fictional-not-a-secret"}),
        media="application/x-www-form-urlencoded",
    )
    assert status == 302 and headers["Location"].startswith(CALLBACK + "?")
    status, _, body = call(
        port, "POST", "/oauth/token",
        urlencode({"grant_type": "authorization_code", "client_id": "fixture-123",
                   "redirect_uri": CALLBACK, "code": "fixture-code",
                   "code_verifier": "B" * 43}),
        media="application/x-www-form-urlencoded",
    )
    assert status == 200 and json.loads(body)["access_token"] == "fixture-only-token"
    assert ("POST", "/oauth/token") in seen


@pytest.mark.parametrize("method,path", [
    ("GET", "/mcp"), ("POST", "/mcp"), ("GET", "/ui"),
    ("GET", "/remote/poll"), ("POST", "/remote/register"),
    ("GET", "/download/example"), ("GET", "/readyz"),
    ("GET", "/healthz"), ("GET", "/docs"), ("GET", "/"),
    ("GET", "//oauth/authorize"), ("GET", "/oauth/%61uthorize"),
    ("GET", "http://localhost/oauth/authorize"),
    ("POST", "/.well-known/oauth-authorization-server"),
    ("GET", "/oauth/register"), ("DELETE", "/oauth/token"),
])
def test_every_non_oauth_route_and_wrong_method_denied_without_upstream(active_servers, method, path):
    port, seen = active_servers
    before = len(seen)
    status, _, _ = call(port, method, path)
    # BaseHTTPRequestHandler normalizes leading '//' before routing;
    # reject remains mandatory, but it may be HTTP 400 rather than 404.
    assert status in (400, 404, 405)
    assert len(seen) == before


def test_host_redirect_registration_and_resource_injection_refused(active_servers):
    port, seen = active_servers
    attempts = [
        ("GET", "/.well-known/oauth-authorization-server", None, None, "attacker.example"),
        ("GET", "/oauth/authorize?" + urlencode({
            **auth_params(), "redirect_uri": "https://attacker.example/cb"}), None, None, None),
        ("GET", "/oauth/authorize?" + urlencode({
            **auth_params(), "resource": "https://attacker.example"}), None, None, None),
        ("GET", "/oauth/authorize?" + urlencode({
            **auth_params(), "code_challenge_method": "plain"}), None, None, None),
        ("GET", "/oauth/authorize?" + urlencode(auth_params()) +
         "&redirect_uri=https%3A%2F%2Fattacker.example", None, None, None),
        ("POST", "/oauth/register", json.dumps({
            "redirect_uris": ["https://attacker.example/callback"]}), "application/json", None),
        ("POST", "/oauth/token", urlencode({
            "grant_type": "authorization_code", "redirect_uri": CALLBACK,
            "code_verifier": "tiny"}), "application/x-www-form-urlencoded", None),
        ("GET", "/.well-known/oauth-protected-resource", None, None, None),
    ]
    for method, url, body, media, host in attempts:
        before = len(seen)
        status, _, _ = call(port, method, url, body=body, media=media,
                            host=host or CONTRACT.hostname)
        assert 400 <= status < 500, (method, url, status)
        assert len(seen) == before


def test_upstream_malicious_redirect_is_never_returned(active_servers):
    port, seen = active_servers
    body = urlencode({**auth_params(), "evil": "1", "pin": "fixture"})
    status, headers, response = call(
        port, "POST", "/oauth/authorize", body,
        media="application/x-www-form-urlencoded",
    )
    assert status == 400
    assert "Location" not in headers
    assert b"attacker.example" not in response


def test_upstream_contract_must_match_both_issuer_and_resource():
    FakeController.seen = []
    FakeController.mismatch = True
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeController)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        with pytest.raises(g.Refusal, match="issuer/endpoints/PKCE"):
            g.check_controller_contract(CONTRACT, port=server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        t.join(timeout=2)
        FakeController.mismatch = False


def test_bad_config_is_rejected_before_any_listener():
    with pytest.raises(g.Refusal):
        g.Contract("https://private-8765.app.github.dev", RESOURCE, (CALLBACK,))
    with pytest.raises(g.Refusal):
        g.Contract(ISSUER, "https://example.com/mcp", (CALLBACK,))
    with pytest.raises(g.Refusal):
        g.Contract(ISSUER, RESOURCE, ("https://attacker.example/cb",))
    with pytest.raises(g.Refusal):
        g.Contract(ISSUER, RESOURCE, ())
    with pytest.raises(g.Refusal):
        g.Contract("http://oauth.example.com", RESOURCE, (CALLBACK,))


def test_no_public_listener_no_other_repos_no_secret_access_in_source():
    source = (HERE / "gateway.py").read_text()
    assert 'GATEWAY_HOST = "127.0.0.1"' in source
    assert 'UPSTREAM_HOST = "127.0.0.1"' in source
    assert "http.client.HTTPConnection(UPSTREAM_HOST, port, timeout=5)" in source
    assert 'os.access("/srv/chatgpt-controller/controller.env", os.R_OK)' in source
    assert "require_dedicated_gateway_identity()" in source
    for prohibited in [
        "0.0.0.0", "/workspaces/", "identity.json",
        "worker.log", "git push", "setfacl", "subprocess.run",
        "allow-plaintext-http", "AUTH_MODE=none",
    ]:
        assert prohibited not in source



def test_gateway_listener_is_loopback_only_and_connection_bounded():
    server = g.BoundedLoopbackServer(
        ("127.0.0.1", 0), g.make_handler(CONTRACT, upstream_port=1),
    )
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert server.request_queue_size == 16
        assert server.daemon_threads is True
        held = [server._connections.acquire(blocking=False) for _ in range(16)]
        assert all(held)
        assert not server._connections.acquire(blocking=False)
        for _ in range(16):
            server._connections.release()
    finally:
        server.server_close()
