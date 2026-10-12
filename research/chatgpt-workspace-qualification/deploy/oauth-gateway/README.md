# Public-only OAuth authorization gateway — security-qualified code, NOT DEPLOYED

This package is an **allowlist-only, loopback-bound OAuth edge**, not a
general-purpose proxy. Its only upstream is the already-running private
`http://127.0.0.1:8765` controller. The gateway has **no** MCP route, remote
worker routes, workspace/file methods, UI routes, port publication logic,
worker enrollment, Git write action, or OpenAI model inference.

**Current state:** software and isolated CI tests only. There is no configured
public HTTPS hostname, edge tunnel, dedicated service account, deployed gateway,
live issuer migration, end-to-end browser OAuth login, or normal-chat invocation.
`/healthz` and `/readyz` on the separate MCP tunnel remain operational but
do not qualify this OAuth path. Do not claim production readiness.

## Proven upstream facts and why the split is necessary

- Pinned backend: `fwerkor/local-shell-mcp` at
  `dec01b9f50f966097ddfc84d357d12a52f238935`.
  `oauth.py` independently implements `issuer_url` and `resource_url`
  from `LOCAL_SHELL_MCP_OAUTH_ISSUER` and `LOCAL_SHELL_MCP_OAUTH_RESOURCE`,
  falling back to `LOCAL_SHELL_MCP_PUBLIC_BASE_URL`. Tokens are HS256 with
  private controller secret, `iss` issuer and `aud` resource.
- Pinned tunnel client: `openai/tunnel-client` `v0.0.15`. It forwards
  MCP and protected-resource metadata but intentionally does **not** expose
  browser-facing `authorization_endpoint`. OpenAI's maintainer confirms this
  in [issue #23](https://github.com/openai/tunnel-client/issues/23).
- Current Codespaces issuer `https://...-8765.app.github.dev` is **GitHub
  private**, not a suitable direct browser+backchannel authorization origin.
  Adding `oauth_trusted_origins` does **not** solve this on its own.

## Intended trust topology

1. ChatGPT gets private MCP through the existing OpenAI Secure MCP Tunnel.
2. The **public browser** and OAuth backchannel call a separately operated
   **HTTPS origin** carrying only these routes:
   `GET /.well-known/oauth-authorization-server`,
   `GET /.well-known/openid-configuration`,
   `POST /oauth/register`,
   `GET|POST /oauth/authorize`,
   `POST /oauth/token`.
3. An explicitly configured outbound HTTPS ingress reaches the dedicated
   **loopback-only** gateway on `127.0.0.1:8781`. This is not a Codespaces
   forwarded public port. External ingress must *not* expose the controller
   on 8765 or the tunnel health/admin UI on 8770.
4. The gateway routes approved OAuth requests to
   `127.0.0.1:8765`. The existing controller retains its **admin PIN, JWT
   signing secret, one-use authorization code store, S256 verification, and
   client registration**. Secrets are never placed in the gateway.
5. The ChatGPT OAuth bearer reaches the private MCP through the
   Secure MCP Tunnel `main` channel, and the controller checks issuer,
   audience, signature and expiry. The worker remains enrolled and isolated.

## Enforcement in gateway.py

- Fixed `127.0.0.1:8781` listener and fixed `127.0.0.1:8765` upstream;
  arbitrary URLs, methods, unknown paths, traversal and MCP/remote/UI routes
  are denied without forwarding.
- An exact, operator-supplied **canonical HTTPS issuer** other than the
  GitHub-private Codespaces origin; exact ChatGPT callback URI allowlist.
  ChatGPT supports the stable callback
  `https://chatgpt.com/connector_platform_oauth_redirect`; other callbacks
  must come from the actual ChatGPT connection management page.
- Request body and query size limits; rejects duplicated form parameters,
  unapproved DCR callbacks, wrong OAuth audience, absent S256 challenge,
  wrong token grant and unapproved upstream redirects.
- Never follows redirects; upstream loopback only; bounded concurrency
  and request/response timeouts; no request body or query logging.
- Before *and during* service operation, checks upstream OAuth metadata
  against exact issuer, OAuth endpoints and tunnel audience. It refuses
  drift instead of rewriting token claims or changing the signing secret.
- `serve` requires a separate unprivileged `chatgpt-oauth-gateway` user
  with no privileged groups, no access to `/workspaces`, worker checkout or
  controller secret file. This account is **not yet staged**.

The public edge must independently enforce correct TLS, hostname,
anti-DDoS/rate limiting and stable DNS/availability. Ingress authorization
is not equivalent to disabling or replacing PIN/PKCE. Treat authorization
codes and POST bodies as secrets; disable request-body, token and full-URL
logging on the edge. Confirm real browser consent, callback delivery and
token exchange. Document DNS, certificate control and rollback mechanics.

OpenAI's documented connector-facing route is
`<OPENAI_MCP_TUNNEL_BASE_URL>/v1/mcp/<tunnel_id>` (not the tunnel
metadata/control-plane path `/v1/tunnel/<tunnel_id>`). For the
current default host, the gateway's pinned audience is
`https://api.openai.com/v1/mcp/tunnel_6acd09e0298481919ac84778501b0aef`. This exact audience is a **candidate** derived from
the documented default base and must still be confirmed from the
actual ChatGPT connector/rewritten protected-resource metadata before
live issuer migration. Do not treat a successful synthetic JWT test as
proof of the product-facing audience. OAuth authorization requests
missing the agreed `resource` are refused.

## Predeployment configuration contract (NOT commands to run on live host)

For a verified HTTPS issuer `https://auth.example.com`, a controller
migration would **later** require these *non-secret* environment values
(the real hostname and *exact ChatGPT-discovered resource* must be verified):

```text
LOCAL_SHELL_MCP_OAUTH_ISSUER=https://auth.example.com
LOCAL_SHELL_MCP_OAUTH_RESOURCE=https://api.openai.com/v1/mcp/tunnel_6acd09e0298481919ac84778501b0aef
```

These values are illustrative and **must not** be applied as-is. Changing
issuer and audience invalidates older bearer tokens and is a security-relevant
controller migration, requiring a rollback plan and fresh tests. Preserve the
current `LOCAL_SHELL_MCP_AUTH_MODE=oauth`, disabled localhost bypass,
existing signing secret, `3600` second token TTL, worker registry, worker
identity and disabled Git push. **Do not restart the controller or reenroll the
worker simply to exercise this package.**

The gateway's `check` command performs read-only issuer/resource validation
against the current private controller. It will correctly **refuse** before
the controller has been migrated. The `serve` command also checks the
dedicated identity and never exposes a public port.

## CI independent verification

- `test_gateway.py`: real disposable HTTP server; denies unknown paths,
  unapproved OAuth callbacks, DCR redirection, wrong resource, wrong methods,
  malformed requests, unsafe upstream redirects and issuer mismatch.
- `real_gateway_e2e.py`: launches **real pinned** `local-shell-mcp` in a
  disposable temporary directory; performs DCR, browser-consent simulation
  including PIN, PKCE S256, one-time code token exchange, JWT audience/issuer
  validation and authenticated private MCP initialization. No real public
  browser/HTTPS or ChatGPT tool call is simulated or asserted.
- Existing backend CI remains mandatory and uses no real Codespace keys or
  accounts.

**Hard promotion gates:** all CI green; chosen HTTPS ingress and hostname
reviewed; dedicated UID installed safely; private-port visibility checked;
gateway denylist verified from outside; real ChatGPT discovery and OAuth
consent/callback/token transfer succeeds; authenticated *ordinary ChatGPT*
MCP tool call is observed; independent no-other-repository access and
persistence tests pass. Until then, **not production ready**.
