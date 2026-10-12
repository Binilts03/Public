#!/usr/bin/env bash
# Start ONLY the Codespaces OAuth controller; worker is not enrolled or started.
# The forwarded port must remain PRIVATE until external OAuth checks succeed.
# Run: sudo bash .../codespaces-start-controller.sh "$CODESPACE_NAME"
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Run with sudo bash, never source this file" >&2
  return 2
fi
set -euo pipefail
umask 077
abort() { echo "BLOCKED: $*" >&2; exit 2; }

CTRL=chatgpt-controller
WORKER=chatgpt-worker
ROOT=/srv/chatgpt-controller
ENTRY=/opt/public-chatgpt-mcp/nondumpable_mcp_entrypoint.py
PYTHON=/opt/public-chatgpt-mcp/venv/bin/python
ENV_FILE="$ROOT/controller.env"
[[ "$EUID" == 0 && "${SUDO_USER:-}" == codespace ]] ||
  abort "run with sudo bash from codespace login"
[[ -x "$PYTHON" && -r "$ENTRY" && -f "$ENV_FILE" ]] ||
  abort "isolated staging not installed"
[[ -f /opt/public-chatgpt-mcp/codespaces-isolation-qualified ]] ||
  abort "isolated Stage 2 was not qualified; run codespaces-qualify-partial.sh before controller startup"
[[ "$(stat -c '%U:%a' /opt/public-chatgpt-mcp/codespaces-isolation-qualified)" == root:600 ]] ||
  abort "isolation qualification evidence is not root-owned and private"
[[ "$(id -u "$CTRL")" != "$(id -u "$WORKER")" ]] || abort "controller and worker are not distinct UIDs"
runuser -u "$WORKER" -- test ! -x /workspaces/Public ||
  abort "worker can traverse original Codespaces checkout; isolation invalid"
runuser -u "$WORKER" -- test ! -w /workspaces/Public ||
  abort "worker can write to original Codespaces checkout; isolation invalid"
runuser -u "$WORKER" -- test ! -r /workspaces/Public/.git/config ||
  abort "worker can read original Codespaces Git config; isolation invalid"
for socket in /var/run/docker.sock /run/docker.sock; do
  if [[ -e "$socket" ]]; then
    runuser -u "$WORKER" -- test ! -r "$socket" ||
      abort "worker can access privileged Docker socket"
  fi
done
[[ $# == 1 && "$1" =~ ^[a-z0-9][a-z0-9-]{3,100}$ ]] ||
  abort "supply the Codespace name via \"\$CODESPACE_NAME\"; do not supply a URL"
PUBLIC_BASE="https://$1-8765.app.github.dev"
if pgrep -u "$CTRL" -f 'nondumpable_mcp_entrypoint.py' >/dev/null 2>&1; then
  abort "controller already running; refusing duplicate start"
fi
# Replace only the preconfigured URL field; preserve controller-only secrets.
# Do not reuse OAuth clients if switching origins without an operator review.
configured="$(grep '^LOCAL_SHELL_MCP_PUBLIC_BASE_URL=' "$ENV_FILE" || true)"
placeholder='LOCAL_SHELL_MCP_PUBLIC_BASE_URL=https://REPLACE-WITH-AUTHORIZED-HOST.invalid'
target="LOCAL_SHELL_MCP_PUBLIC_BASE_URL=$PUBLIC_BASE"
if [[ "$configured" != "$placeholder" && "$configured" != "$target" ]]; then
  abort "controller is configured for a different origin; manual review required"
fi
if [[ "$configured" != "LOCAL_SHELL_MCP_PUBLIC_BASE_URL=$PUBLIC_BASE" ]]; then
  temp="$(mktemp "$ROOT/controller.env.XXXXXXXX")"
  sed "s|^LOCAL_SHELL_MCP_PUBLIC_BASE_URL=.*$|LOCAL_SHELL_MCP_PUBLIC_BASE_URL=$PUBLIC_BASE|" "$ENV_FILE" > "$temp"
  chown "$CTRL:$CTRL" "$temp"
  chmod 0600 "$temp"
  mv -f "$temp" "$ENV_FILE"
fi
grep -qx 'LOCAL_SHELL_MCP_DISABLE_LOCAL=true' "$ENV_FILE" ||
  abort "local command execution was not disabled"
grep -qx 'LOCAL_SHELL_MCP_AUTH_MODE=oauth' "$ENV_FILE" ||
  abort "OAuth must remain enabled"
grep -qx 'LOCAL_SHELL_MCP_AUTH_BYPASS_LOCALHOST=false' "$ENV_FILE" ||
  abort "OAuth localhost bypass must remain disabled"
runuser -u "$WORKER" -- test ! -r "$ENV_FILE" ||
  abort "worker can access controller credentials"
# Real runtime access is mandatory; root executable checks are insufficient.
if ! runuser -u "$CTRL" -- env -i HOME="$ROOT/home" \
  PATH=/opt/public-chatgpt-mcp/venv/bin:/usr/bin:/bin \
  PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -c 'import local_shell_mcp.main' \
  >/dev/null 2>&1; then
  abort "controller cannot import backend runtime; run codespaces-repair-runtime.py"
fi
if ss -ltn 2>/dev/null | grep -Eq '(:8765)[[:space:]]'; then
  abort "port 8765 already has a listener"
fi

if [[ -e "$ROOT/logs/controller.log" ]]; then
  [[ "$(stat -c '%U:%a' "$ROOT/logs/controller.log")" == "$CTRL:600" ]] ||
    abort "controller log permissions unexpected; preserve it for audit"
else
  install -o "$CTRL" -g "$CTRL" -m 0600 /dev/null "$ROOT/logs/controller.log"
fi
echo "Starting OAuth controller on 127.0.0.1:8765 (no worker; no port visibility changes)"
runuser -u "$CTRL" -- env -i \
  HOME="$ROOT/home" XDG_CONFIG_HOME="$ROOT/home/.config" \
  PATH=/opt/public-chatgpt-mcp/venv/bin:/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  /usr/bin/nohup /bin/bash -c \
  'set -a; . /srv/chatgpt-controller/controller.env; set +a; exec /opt/public-chatgpt-mcp/venv/bin/python /opt/public-chatgpt-mcp/nondumpable_mcp_entrypoint.py --mode mcp --remote' \
  >> "$ROOT/logs/controller.log" 2>&1 < /dev/null &
for attempt in $(seq 1 70); do
  if curl --silent --fail --max-time 2 http://127.0.0.1:8765/healthz >/dev/null; then break; fi
  sleep 0.3
done
curl --silent --fail --max-time 5 http://127.0.0.1:8765/healthz >/dev/null ||
  abort "controller failed health check; inspect protected logs locally"
curl --silent --fail --max-time 5 http://127.0.0.1:8765/.well-known/oauth-authorization-server |
  "$PYTHON" -c 'import json,sys; x=json.load(sys.stdin); assert x["issuer"]==sys.argv[1], "OAuth issuer mismatch"; assert "S256" in x["code_challenge_methods_supported"], "PKCE missing"' "$PUBLIC_BASE" ||
  abort "OAuth discovery validation failed"
http_code="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' --max-time 5 \
  -X POST http://127.0.0.1:8765/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"no-auth-probe","version":"1"}}}')"
[[ "$http_code" == 401 ]] || abort "unauthenticated MCP request returned HTTP $http_code (expected 401)"
[[ -n "$(pgrep -u "$CTRL" -f 'nondumpable_mcp_entrypoint.py' || true)" ]] ||
  abort "controller process disappeared"
for pid in $(pgrep -u "$CTRL" -f 'nondumpable_mcp_entrypoint.py'); do
  runuser -u "$WORKER" -- test ! -r "/proc/$pid/environ" ||
    abort "worker can read controller process environment"
done
echo 'LOCAL_CONTROLLER_GATE_PASS OAuth metadata, PKCE, unauthenticated denial, and separate UID.'
echo "PUBLIC_BASE=$PUBLIC_BASE"
echo "MCP_URL=$PUBLIC_BASE/mcp"
echo 'PORT_VISIBILITY_UNCHANGED: Codespaces forwarded port is not made public by this script.'
echo 'CONTROLLER_ONLY: this script does not start the worker; existing enrollment is preserved.'
echo 'OAuth admin PIN is stored in controller.env; do not paste it into GitHub, chat or logs.'
