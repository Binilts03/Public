#!/usr/bin/env python3
"""OFFLINE render/validate: locally managed Cloudflare named-tunnel OAuth ingress.

No Cloudflare API, DNS operation, login, credential creation or daemon start.
Strictly matches the five approved OAuth routes and otherwise returns 404.
"""
from __future__ import annotations

import argparse
import uuid

from qualify_ingress import validate_public_hostname
from gateway import Refusal, require

OAUTH_ONLY_PATH_REGEX = (
    r"^/(?:\.well-known/(?:oauth-authorization-server|openid-configuration)"
    r"|oauth/(?:register|authorize|token))$"
)
CREDENTIAL_DIR = "/srv/chatgpt-oauth-edge/credentials"
GATEWAY_SERVICE = "http://127.0.0.1:8781"


def render(issuer: str, tunnel_uuid: str) -> str:
    hostname = validate_public_hostname(issuer)
    parsed_uuid = uuid.UUID(tunnel_uuid)
    require(str(parsed_uuid) == tunnel_uuid, "tunnel UUID must be canonical")
    # YAML scalar fields are entirely sanitized by hostname and UUID checks.
    return (
        "# OAuth-only edge. Off-line template; DO NOT run without security gates.\n"
        f"tunnel: {tunnel_uuid}\n"
        f"credentials-file: {CREDENTIAL_DIR}/{tunnel_uuid}.json\n"
        "ingress:\n"
        f"  - hostname: {hostname}\n"
        f"    path: '{OAUTH_ONLY_PATH_REGEX}'\n"
        f"    service: {GATEWAY_SERVICE}\n"
        "    originRequest:\n"
        f"      httpHostHeader: {hostname}\n"
        "      connectTimeout: 5s\n"
        "      disableChunkedEncoding: true\n"
        "  - service: http_status:404\n"
    )


def validate_structure(document: str, *, issuer: str, tunnel_uuid: str) -> None:
    """Reject edits to the renderer output: no accidental catchall exposure."""
    require(document == render(issuer, tunnel_uuid),
            "OAuth ingress differs from reviewed, exact allowlist")
    require(document.count("service: http://") == 1
            and document.count("service: http_status:404") == 1,
            "OAuth ingress must have exactly one loopback service and default deny")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issuer", required=True, help="Reviewed canonical HTTPS OAuth hostname")
    parser.add_argument("--tunnel-uuid", required=True,
                        help="Pre-existing Cloudflare named tunnel UUID (not OpenAI tunnel ID)")
    args = parser.parse_args()
    result = render(args.issuer, args.tunnel_uuid)
    validate_structure(result, issuer=args.issuer, tunnel_uuid=args.tunnel_uuid)
    print(result, end="")


if __name__ == "__main__":
    try:
        main()
    except (Refusal, ValueError) as exc:
        print("BLOCKED: malformed ingress inputs (" + type(exc).__name__ + ")")
        raise SystemExit(2) from None
