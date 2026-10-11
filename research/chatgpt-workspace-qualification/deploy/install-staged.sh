#!/usr/bin/env bash
# STAGED ONLY: Ubuntu 24.04 VM prepared exclusively for Binilts03/Public.
# Does not connect ChatGPT, start an MCP service, publish ports, or push Git.
set -euo pipefail
umask 077
if [[ "$(id -u)" -ne 0 ]]; then echo "Run with sudo on a disposable Ubuntu VM." >&2; exit 2; fi
HERE="$(cd -- "$(dirname -- "$0")" && pwd -P)"
UPSTREAM_SHA="dec01b9f50f966097ddfc84d357d12a52f238935"
ROOT="/srv/chatgpt-coder"
SERVICE_USER="chatgpt-coder"
for cmd in git python3 openssl runuser systemctl; do
  command -v "$cmd" >/dev/null || { echo "Missing tool: $cmd" >&2; exit 3; }
done
[[ -e "$HERE/nondumpable_mcp_entrypoint.py" && -e "$HERE/chatgpt-coder.service" ]] ||
  { echo "Deployment package incomplete" >&2; exit 4; }
[[ -d /run/systemd/system ]] || { echo "Requires systemd host" >&2; exit 5; }
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --user-group --home-dir "$ROOT/home" --shell /usr/sbin/nologin "$SERVICE_USER"
fi
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 \
  "$ROOT" "$ROOT/home" "$ROOT/state" "$ROOT/skills" "$ROOT/git" "$ROOT/worktrees"
install -d -o root -g root -m 0755 /opt/chatgpt-coder
install -d -o root -g root -m 0700 /etc/chatgpt-coder
if [[ ! -d /opt/chatgpt-coder/source/.git ]]; then
  git clone --filter=blob:none https://github.com/fwerkor/local-shell-mcp.git /opt/chatgpt-coder/source
fi
git -C /opt/chatgpt-coder/source fetch origin "$UPSTREAM_SHA"
git -C /opt/chatgpt-coder/source checkout --detach "$UPSTREAM_SHA"
[[ "$(git -C /opt/chatgpt-coder/source rev-parse HEAD)" == "$UPSTREAM_SHA" ]] ||
  { echo "Upstream SHA pin mismatch" >&2; exit 6; }
if [[ ! -x /opt/chatgpt-coder/venv/bin/python ]]; then python3 -m venv /opt/chatgpt-coder/venv; fi
/opt/chatgpt-coder/venv/bin/python -m pip install --disable-pip-version-check \
  /opt/chatgpt-coder/source
install -o root -g root -m 0755 "$HERE/nondumpable_mcp_entrypoint.py" \
  /opt/chatgpt-coder/nondumpable_mcp_entrypoint.py
if [[ ! -d "$ROOT/git/Public/.git" ]]; then
  runuser -u "$SERVICE_USER" -- git clone --filter=blob:none \
    https://github.com/Binilts03/Public.git "$ROOT/git/Public"
fi
if [[ ! -d "$ROOT/worktrees/Public" ]]; then
  runuser -u "$SERVICE_USER" -- git -C "$ROOT/git/Public" \
    worktree add --detach "$ROOT/worktrees/Public" HEAD
fi
runuser -u "$SERVICE_USER" -- git -C "$ROOT/git/Public" \
  remote set-url --push origin no-push://disabled
runuser -u "$SERVICE_USER" -- git -C "$ROOT/worktrees/Public" \
  config user.name "ChatGPT Qualifier"
runuser -u "$SERVICE_USER" -- git -C "$ROOT/worktrees/Public" \
  config user.email "chatgpt-qualifier@example.invalid"
if [[ ! -e /etc/chatgpt-coder/runtime.env ]]; then
  PIN="$(openssl rand -hex 32)"
  JWT="$(openssl rand -hex 48)"
  cat > /etc/chatgpt-coder/runtime.env <<EOF
LOCAL_SHELL_MCP_MODE=mcp
LOCAL_SHELL_MCP_HOST=127.0.0.1
LOCAL_SHELL_MCP_PORT=8765
LOCAL_SHELL_MCP_WORKSPACE_ROOT=$ROOT/worktrees/Public
LOCAL_SHELL_MCP_STATE_DIR=$ROOT/state
LOCAL_SHELL_MCP_AGENT_CONFIG_DIR=$ROOT/skills
LOCAL_SHELL_MCP_AUTH_MODE=oauth
LOCAL_SHELL_MCP_AUTH_BYPASS_LOCALHOST=false
LOCAL_SHELL_MCP_REQUIRE_AUTH_FOR_MCP_DISCOVERY=true
LOCAL_SHELL_MCP_OAUTH_ACCESS_TOKEN_TTL_S=86400
LOCAL_SHELL_MCP_PUBLIC_BASE_URL=https://REPLACE-WITH-AUTHORIZED-HOST.invalid
LOCAL_SHELL_MCP_OAUTH_ADMIN_PIN=$PIN
LOCAL_SHELL_MCP_OAUTH_JWT_SECRET=$JWT
LOCAL_SHELL_MCP_REMOTE_ENABLED=false
LOCAL_SHELL_MCP_REMOTE_PEER_TRANSFER_ENABLED=false
LOCAL_SHELL_MCP_ALLOW_FULL_CONTAINER=false
LOCAL_SHELL_MCP_UI_ENABLED=false
LOCAL_SHELL_MCP_LIVE_WORKSPACE_ENABLED=false
LOCAL_SHELL_MCP_MAX_CONCURRENT_COMMANDS=2
EOF
fi
chown root:root /etc/chatgpt-coder/runtime.env
chmod 0600 /etc/chatgpt-coder/runtime.env
install -o root -g root -m 0644 "$HERE/chatgpt-coder.service" \
  /etc/systemd/system/chatgpt-coder.service
systemctl daemon-reload
systemctl disable chatgpt-coder.service >/dev/null 2>&1 || true
echo "STAGED: Only Binilts03/Public cloned. No push; server not started."
echo "STOP: Do not start service or publish Tailscale Funnel before state-file isolation."
