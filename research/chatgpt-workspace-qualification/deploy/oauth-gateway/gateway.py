#!/usr/bin/env python3
"""Narrow, loopback-only OAuth ingress for the Public Codespace controller.

NOT an MCP proxy. The HTTPS edge/ingress and its deployment are separate
qualification gates. No action is taken on import. This script never reads
controller secrets or worker state, starts a public listener, or changes Git.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import os
import pwd
import json
import re
import threading
from urllib.parse import parse_qs, urlsplit

UPSTREAM_HOST = "127.0.0.1"
UPSTREAM_PORT = 8765
GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 8781
MAX_REQUEST = 16_384
MAX_RESPONSE = 262_144
MAX_QUERY = 4_096
ALLOWED = {
    "/.well-known/oauth-authorization-server": {"GET"},
    "/.well-known/openid-configuration": {"GET"},
    "/oauth/register": {"POST"},
    "/oauth/authorize": {"GET", "POST"},
    "/oauth/token": {"POST"},
}
CHALLENGE = re.compile(r"[A-Za-z0-9_-]{43,128}\Z")
TUNNEL_RESOURCE = re.compile(
    r"https://api\.openai\.com/v1/tunnel/tunnel_[0-9a-f]{32}(?:/mcp)?\Z"
)


class Refusal(Exception):
    pass


def require(predicate: bool, message: str) -> None:
    if not predicate:
        raise Refusal(message)


def unique_form(body: str) -> dict[str, str]:
    try:
        pairs = parse_qs(body, keep_blank_values=True, strict_parsing=True, max_num_fields=36)
    except ValueError:
        raise Refusal("invalid form encoding") from None
    require(all(len(v) == 1 for v in pairs.values()), "duplicate parameter")
    return {k: v[0] for k, v in pairs.items()}


def exact_origin(value: str) -> str:
    parts = urlsplit(value)
    require(parts.scheme == "https" and bool(parts.hostname)
            and parts.username is None and parts.password is None
            and parts.path in ("", "/") and not parts.query and not parts.fragment
            and parts.port in (None, 443),
            "gateway issuer must be a plain HTTPS origin")
    hostname = parts.hostname.lower()
    require(not hostname.endswith(".app.github.dev")
            and hostname not in {"localhost", "127.0.0.1"}
            and "." in hostname,
            "gateway issuer cannot be the private Codespaces URL or loopback")
    require(value == "https://" + hostname, "gateway issuer must be canonical HTTPS origin")
    return hostname


@dataclass(frozen=True)
class Contract:
    issuer: str
    resource: str
    redirects: tuple[str, ...]

    def __post_init__(self) -> None:
        exact_origin(self.issuer)
        require(bool(TUNNEL_RESOURCE.fullmatch(self.resource)),
                "resource must be the explicit OpenAI tunnel MCP audience")
        require(0 < len(self.redirects) <= 6 and len(set(self.redirects)) == len(self.redirects),
                "configure one to six distinct exact ChatGPT callback URLs")
        for url in self.redirects:
            p = urlsplit(url)
            require(p.scheme == "https" and p.netloc == "chatgpt.com"
                    and not p.query and not p.fragment
                    and (p.path == "/connector_platform_oauth_redirect"
                         or bool(re.fullmatch(r"/connector/oauth/[A-Za-z0-9_-]+", p.path))),
                    "callback must match an exact ChatGPT connector redirect URI")

    @property
    def hostname(self) -> str:
        return exact_origin(self.issuer)

    def enforce_params(self, route: str, method: str, params: dict[str, str]) -> None:
        if route == "/oauth/register":
            return
        if route in ("/oauth/authorize", "/oauth/token"):
            require(params.get("redirect_uri") in self.redirects,
                    "unapproved OAuth redirect URI")
            resource = params.get("resource")
            require(resource is None or resource == self.resource,
                    "OAuth resource audience mismatch")
        if route == "/oauth/authorize":
            require(params.get("response_type") == "code"
                    and params.get("code_challenge_method") == "S256"
                    and bool(CHALLENGE.fullmatch(params.get("code_challenge", ""))),
                    "authorization must use PKCE S256")
        if route == "/oauth/token":
            require(params.get("grant_type") == "authorization_code"
                    and bool(CHALLENGE.fullmatch(params.get("code_verifier", ""))),
                    "token exchange must use authorization code with PKCE")

    def enforce_registration(self, payload: bytes) -> None:
        try:
            registration = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            raise Refusal("invalid registration JSON") from None
        require(isinstance(registration, dict), "registration body must be an object")
        redirects = registration.get("redirect_uris")
        require(isinstance(redirects, list) and bool(redirects)
                and len(redirects) <= len(self.redirects)
                and all(isinstance(x, str) and x in self.redirects for x in redirects),
                "DCR requested an unapproved redirect URI")
        require(registration.get("token_endpoint_auth_method", "none") == "none",
                "only PKCE public clients are allowed")

    def enforce_callback(self, location: str) -> None:
        p = urlsplit(location)
        callback = p._replace(query="", fragment="").geturl()
        require(callback in self.redirects and not p.fragment,
                "upstream attempted an unapproved OAuth redirect")
        params = unique_form(p.query)
        require(params.get("iss") == self.issuer
                and bool(params.get("code")) and len(params["code"]) <= 512,
                "upstream authorization redirect did not identify expected issuer")


def request_upstream(method: str, path: str, body: bytes | None = None,
                     content_type: str = "", *, port: int = UPSTREAM_PORT):
    """Fixed loopback destination; never follows redirects or uses env proxies."""
    conn = http.client.HTTPConnection(UPSTREAM_HOST, port, timeout=5)
    try:
        headers = {"Host": f"{UPSTREAM_HOST}:{port}", "Accept-Encoding": "identity",
                   "Connection": "close"}
        if body is not None:
            headers["Content-Type"] = content_type
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        data = response.read(MAX_RESPONSE + 1)
        require(len(data) <= MAX_RESPONSE, "upstream OAuth response too large")
        require(response.getheader("Content-Encoding", "identity") in ("identity", ""),
                "encoded OAuth responses are unsupported")
        # ASGI/Uvicorn commonly emits lowercase header names. HTTP header
        # lookup must be case-insensitive, particularly Location and media.
        return response.status, {k.lower(): v for k, v in response.getheaders()}, data
    finally:
        conn.close()


def check_controller_contract(contract: Contract, *, port: int = UPSTREAM_PORT) -> None:
    """Fail closed on issuer/audience drift before accepting any OAuth traffic."""
    for path in ("/.well-known/oauth-authorization-server",
                 "/.well-known/oauth-protected-resource"):
        status, _, body = request_upstream("GET", path, port=port)
        require(status == 200, "private OAuth metadata unavailable")
        try:
            data = json.loads(body)
        except ValueError:
            raise Refusal("private OAuth metadata is not valid JSON") from None
        if path.endswith("oauth-authorization-server"):
            require(data.get("issuer") == contract.issuer
                    and data.get("authorization_endpoint") == contract.issuer + "/oauth/authorize"
                    and data.get("token_endpoint") == contract.issuer + "/oauth/token"
                    and data.get("registration_endpoint") == contract.issuer + "/oauth/register"
                    and "S256" in data.get("code_challenge_methods_supported", []),
                    "controller OAuth issuer/endpoints/PKCE do not match approved gateway")
        else:
            require(data.get("authorization_servers") == [contract.issuer]
                    and data.get("resource") == contract.resource,
                    "private resource audience/authorization-server mismatch")


def make_handler(contract: Contract, *, upstream_port: int = UPSTREAM_PORT):
    slots = threading.BoundedSemaphore(8)

    class GatewayHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"
        server_version = "OAuthOnlyGateway"
        sys_version = ""

        def parse_request(self):
            # BaseHTTPRequestHandler normalizes leading '//' to '/', so
            # inspect the original request-target before dispatch. Parse
            # first to initialize the HTTP version for a valid 400 response.
            if not super().parse_request():
                return False
            raw = self.raw_requestline.split(b" ", 2)
            if len(raw) >= 2 and raw[1].startswith(b"//"):
                self.send_error(400, "Invalid request target")
                return False
            return True

        def log_message(self, fmt, *args):
            # Never log query strings, authorization codes, PINs, bearer tokens.
            pass

        def _reply(self, status: int, payload: bytes, content_type: str = "application/json",
                   location: str | None = None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            if content_type.startswith("text/html"):
                self.send_header("Content-Security-Policy",
                                 "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
                                 "form-action 'self'; frame-ancestors 'none'")
            if location is not None:
                self.send_header("Location", location)
            self.end_headers()
            self.wfile.write(payload)

        def _block(self, status=404):
            self._reply(status, b'{"error":"request_not_allowed"}')

        def _handle(self, method):
            if not slots.acquire(blocking=False):
                self._block(503)
                return
            try:
                host = self.headers.get("Host", "")
                if host not in (contract.hostname, contract.hostname + ":443"):
                    self._block(421)
                    return
                if len(self.path) > MAX_QUERY + 96:
                    self._block(414)
                    return
                url = urlsplit(self.path)
                route = url.path
                if url.scheme or url.netloc or route not in ALLOWED:
                    self._block()
                    return
                if method not in ALLOWED[route]:
                    self._block(405)
                    return
                if self.headers.get_all("Content-Length", []) and method == "GET":
                    self._block(400)
                    return
                if self.headers.get_all("Transfer-Encoding", []):
                    self._block(400)
                    return
                if len(self.headers.get_all("Content-Length", [])) > 1:
                    self._block(400)
                    return
                if len(url.query) > MAX_QUERY:
                    self._block(414)
                    return
                params = unique_form(url.query) if url.query else {}
                body = None
                media = ""
                if method == "POST":
                    raw_len = self.headers.get("Content-Length", "")
                    require(raw_len.isascii() and raw_len.isdecimal(), "missing body length")
                    size = int(raw_len)
                    require(0 < size <= MAX_REQUEST, "request body over budget")
                    media = self.headers.get("Content-Type", "").split(";", 1)[0].lower().strip()
                    expected = ("application/json" if route == "/oauth/register"
                                else "application/x-www-form-urlencoded")
                    require(media == expected, "unsupported OAuth content type")
                    body = self.rfile.read(size)
                    require(len(body) == size, "truncated body")
                    if route == "/oauth/register":
                        contract.enforce_registration(body)
                    else:
                        params = unique_form(body.decode("utf-8"))
                elif url.query and route != "/oauth/authorize":
                    raise Refusal("metadata discovery has unexpected query")
                contract.enforce_params(route, method, params)
                # Re-check on every allowed OAuth operation; stale issuer or
                # resource configuration must fail closed across restarts.
                check_controller_contract(contract, port=upstream_port)
                status, response_headers, data = request_upstream(
                    method, self.path, body, media, port=upstream_port)
                location = response_headers.get("location")
                if location:
                    require(route == "/oauth/authorize" and method == "POST"
                            and status == 302, "unexpected upstream redirect")
                    contract.enforce_callback(location)
                require(status != 302 or location is not None, "missing redirect location")
                response_media = response_headers.get("content-type", "application/json")
                require(response_media.split(";", 1)[0] in ("text/html", "application/json"),
                        "upstream content type not allowed")
                self._reply(status, data, response_media, location)
            except (Refusal, UnicodeDecodeError, ValueError, OSError, http.client.HTTPException):
                self._block(400)
            finally:
                slots.release()

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def do_PUT(self):
            self._block()

        def do_DELETE(self):
            self._block()

        def do_PATCH(self):
            self._block()

        def do_OPTIONS(self):
            self._block()

        def do_HEAD(self):
            self._block(405)

    return GatewayHandler


def require_dedicated_gateway_identity() -> None:
    # The edge-facing OAuth process must never inherit Codespaces credentials
    # or the registered worker's filesystem/privileged Linux groups.
    user = pwd.getpwuid(os.geteuid())
    require(user.pw_name == "chatgpt-oauth-gateway" and os.geteuid() != 0,
            "serve requires an isolated unprivileged chatgpt-oauth-gateway user")
    require(user.pw_shell == "/usr/sbin/nologin",
            "gateway account must have a nologin shell")
    import grp
    group_names = {grp.getgrgid(gid).gr_name for gid in os.getgroups()}
    require(user.pw_name not in ("chatgpt-controller", "chatgpt-worker"),
            "gateway must have a distinct controller/worker identity")
    require(not os.access("/workspaces", os.X_OK)
            and not os.access("/srv/chatgpt-controller/controller.env", os.R_OK)
            and not os.access("/srv/chatgpt-worker/worktrees/Public", os.X_OK),
            "gateway can reach protected controller/worker filesystem")
    require(not group_names.intersection({"root", "sudo", "docker", "ssh", "codespace"}),
            "gateway has a forbidden privileged group")


class BoundedLoopbackServer(ThreadingHTTPServer):
    """Reject excess sockets before spawning handler threads.

    Bound concurrency and header-read timeouts protect the private gateway
    even if the external TLS ingress is misconfigured or rate limiting fails.
    """
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, server_address, handler_class):
        self._connections = threading.BoundedSemaphore(16)
        super().__init__(server_address, handler_class)

    def process_request(self, request, client_address):
        request.settimeout(6)
        if not self._connections.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._connections.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connections.release()


def main() -> None:
    parser = argparse.ArgumentParser(description="Strict OAuth-only loopback ingress")
    parser.add_argument("command", choices=("check", "serve"))
    parser.add_argument("--issuer", required=True, help="Separately controlled HTTPS OAuth origin")
    parser.add_argument("--resource", required=True, help="Exact OpenAI tunnel MCP audience")
    parser.add_argument("--redirect-uri", action="append", required=True,
                        help="Exact approved ChatGPT callback (may repeat)")
    args = parser.parse_args()
    contract = Contract(args.issuer, args.resource, tuple(args.redirect_uri))
    check_controller_contract(contract)
    if args.command == "check":
        print("OAUTH_GATEWAY_CONTROLLER_CONTRACT_PASS_NO_NETWORK_LISTENER")
        return
    require_dedicated_gateway_identity()
    print("OAUTH_GATEWAY_LOOPBACK_ONLY_READY_UNQUALIFIED_EXTERNAL_INGRESS", flush=True)
    server = BoundedLoopbackServer((GATEWAY_HOST, GATEWAY_PORT), make_handler(contract))
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    try:
        main()
    except Refusal as exc:
        print("BLOCKED: " + str(exc))
        raise SystemExit(2) from None
