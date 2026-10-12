#!/usr/bin/env python3
"""Read-only, non-secret local/external preflight for OAuth-only HTTPS ingress.

Never edits the controller, tunnel, registered worker, git, port visibility,
secrets, DNS or Cloudflare. Does not perform authorization or issue tokens.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import pwd
import sys
from pathlib import Path
import socket
import ssl
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gateway import (
    Contract, Refusal, GATEWAY_PORT, MAX_RESPONSE,
    require, exact_origin, request_upstream,
)

CONTROLLER_PORT = 8765
TUNNEL_HEALTH_PORT = 8770

DENIED_PATHS = (
    "/mcp", "/remote/poll", "/remote/register", "/ui",
    "/healthz", "/readyz", "/download/fixture",
    "/docs", "/metrics", "/",
)


def _local_get(path: str, *, port: int, timeout: float = 3):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        data = response.read(MAX_RESPONSE + 1)
        require(len(data) <= MAX_RESPONSE, "local response exceeds size limit")
        return response.status, data
    finally:
        conn.close()


def expected_matches(metadata: dict, *, issuer: str, resource: str) -> bool:
    return metadata.get("issuer") == issuer and metadata.get("resource") == resource


def local_report(*, controller_port=CONTROLLER_PORT,
                 health_port=TUNNEL_HEALTH_PORT,
                 gateway_port=GATEWAY_PORT,
                 expected_issuer: str | None = None,
                 expected_resource: str | None = None) -> list[str]:
    """Report only states, never payload, PIN, key material or OAuth codes."""
    messages = []
    for label, port in (("controller_health", controller_port),
                        ("tunnel_ready", health_port)):
        route = "/healthz" if label == "controller_health" else "/readyz"
        try:
            status, _ = _local_get(route, port=port)
        except OSError:
            messages.append(label.upper() + "_UNREACHABLE")
        else:
            messages.append(label.upper() + ("_PASS" if status == 200 else "_NOT_READY"))
    try:
        _, _, body = request_upstream("GET", "/.well-known/oauth-authorization-server",
                                      port=controller_port)
        _, _, prmd = request_upstream("GET", "/.well-known/oauth-protected-resource",
                                      port=controller_port)
        auth, resource = json.loads(body), json.loads(prmd)
        public = auth.get("issuer", "")
        aud = resource.get("resource", "")
        messages.append(
            "CONTROLLER_ISSUER_CODESPACES_PRIVATE" if
            isinstance(public, str) and public.endswith(".app.github.dev")
            else "CONTROLLER_ISSUER_OTHER"
        )
        messages.append(
            "CONTROLLER_RESOURCE_CODESPACES_PRIVATE" if
            isinstance(aud, str) and ".app.github.dev" in aud
            else "CONTROLLER_RESOURCE_OTHER"
        )
        messages.append(
            "CONTROLLER_PKCE_S256_" +
            ("PASS" if "S256" in auth.get("code_challenge_methods_supported", [])
             else "MISSING")
        )
        if expected_issuer is not None and expected_resource is not None:
            expected = auth.get("issuer") == expected_issuer and aud == expected_resource
            messages.append(
                "CONTROLLER_MIGRATION_CONTRACT_" +
                ("MATCH" if expected else "MISMATCH_NO_WRITE"))
    except (OSError, ValueError, KeyError, Refusal):
        messages.append("CONTROLLER_METADATA_UNAVAILABLE")
    try:
        p = pwd.getpwnam("chatgpt-oauth-gateway")
    except KeyError:
        messages.append("GATEWAY_SERVICE_UID_NOT_STAGED")
    else:
        messages.append("GATEWAY_SERVICE_UID_PRESENT_UNVERIFIED")
    with socket.socket() as s:
        s.settimeout(1)
        if s.connect_ex(("127.0.0.1", gateway_port)) == 0:
            messages.append("GATEWAY_LOOPBACK_LISTENER_PRESENT_UNVERIFIED")
        else:
            messages.append("GATEWAY_LOOPBACK_LISTENER_NOT_STARTED")
    messages.append("CODESPACES_PORT_VISIBILITY_NOT_VERIFIABLE_HERE")
    messages.append("NO_KEYS_READ_NO_MUTATION_NO_EXTERNAL_REQUESTS")
    return messages


def validate_public_hostname(issuer: str) -> str:
    hostname = exact_origin(issuer)
    require(not hostname.endswith((".test", ".invalid", ".localhost", ".local", ".internal")),
            "public issuer cannot be a test or internal DNS name")
    import ipaddress
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return hostname
    raise Refusal("public issuer must be a DNS hostname, not an IP address")


def external_https_fetch(hostname: str, path: str, *, timeout: float=7.0):
    """Verified TLS, no env proxies, no redirects, no bearer or other credentials."""
    require(path.startswith("/") and not path.startswith("//")
            and "?" not in path and "#" not in path,
            "external inspection is restricted to fixed paths")
    conn = http.client.HTTPSConnection(
        hostname, 443, timeout=timeout,
        context=ssl.create_default_context(),
    )
    try:
        conn.request("GET", path, headers={
            "Host": hostname, "Accept": "application/json",
            "Accept-Encoding": "identity",
        })
        response = conn.getresponse()
        data = response.read(MAX_RESPONSE + 1)
        require(len(data) <= MAX_RESPONSE, "public OAuth response too large")
        return response.status, dict(response.getheaders()), data
    finally:
        conn.close()


def external_report(issuer: str, *, fetch=external_https_fetch) -> list[str]:
    hostname = validate_public_hostname(issuer)
    messages = []
    status, headers, body = fetch(hostname, "/.well-known/oauth-authorization-server")
    require(status == 200, "public OAuth AS metadata is unavailable over verified HTTPS")
    require(len(body) <= MAX_RESPONSE, "public OAuth metadata over limit")
    try:
        meta = json.loads(body)
    except ValueError:
        raise Refusal("public OAuth AS metadata is not JSON") from None
    require(meta.get("issuer") == issuer
            and meta.get("authorization_endpoint") == issuer + "/oauth/authorize"
            and meta.get("token_endpoint") == issuer + "/oauth/token"
            and meta.get("registration_endpoint") == issuer + "/oauth/register"
            and "S256" in meta.get("code_challenge_methods_supported", []),
            "public OAuth endpoints, issuer, or PKCE do not match approved contract")
    messages.append("EXTERNAL_HTTPS_TLS_AND_AS_METADATA_PASS")
    for path in DENIED_PATHS:
        status, headers, data = fetch(hostname, path)
        require(status in (404, 405), "public gateway exposed or redirected non-OAuth route")
        require(not any(k.lower() == "location" for k in headers),
                "public non-OAuth path redirected")
    messages.append("EXTERNAL_MCP_WORKER_UI_HEALTH_DENIAL_PASS")
    messages.append("PUBLIC_INGRESS_READ_ONLY_PREFLIGHT_PASS")
    messages.append("NO_CREDENTIALS_SENT_NO_AUTH_CODES_NO_CONTROLLER_CHANGES")
    return messages


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("local", "external"))
    parser.add_argument("--issuer", help="Exact reviewed HTTPS OAuth-only origin")
    parser.add_argument("--resource", help="Exact anticipated MCP resource audience (local mode only)")
    args = parser.parse_args()
    if args.mode == "local":
        require(bool(args.issuer) == bool(args.resource),
                "pass both --issuer and --resource for migration comparison")
        if args.issuer:
            exact_origin(args.issuer)
        messages = local_report(expected_issuer=args.issuer, expected_resource=args.resource)
    else:
        require(args.issuer is not None and not args.resource,
                "external preflight requires only the public HTTPS issuer")
        messages = external_report(args.issuer)
    for item in messages:
        print(item)


if __name__ == "__main__":
    try:
        main()
    except (Refusal, OSError, ssl.SSLError, ValueError) as exc:
        # An error can contain sensitive URLs; only show our own static reason.
        if isinstance(exc, Refusal):
            print("BLOCKED: " + str(exc))
        else:
            print("BLOCKED: preflight failure " + type(exc).__name__)
        raise SystemExit(2) from None
