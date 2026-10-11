#!/usr/bin/env bash
# STAGING ONLY — does NOT start a service, enroll a worker or expose HTTPS.
# Scope: only Binilts03/Public. Run only on a dedicated, disposable Ubuntu VM.
set -euo pipefail
umask 077

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Use sudo on a dedicated disposable Ubuntu VM." >&2
  exit 2
fi
HERE="$(cd -- "$(dirname -- "$0")" && pwd -P)"
PIN="dec01b9f50f966097ddfc84d357d12a52f238935"
CTRL="chatgpt-controller"
WORKER="chatgpt-worker"
CTRL_ROOT="/srv/chatgpt-controller"
WORKER_ROOT="/srv/chatgpt-worker"
CONFIG_DIR="/etc/chatgpt-coder"
OPT_DIR="/opt/chatgpt-coder"
for bin in git python3 openssl runuser systemctl install useradd; do
  command -v "$bin" >/dev/null || { echo "Missing prerequisite: $bin" >&2; exit 3; }
done
for name in nondumpable_mcp_entrypoint.py chatgpt-coder.service chatgpt-worker.service; do
  [[ -f "$HERE/$name" ]] || { echo "Missing staging file: $name" >&2; exit 4; }
done
[[ -d /run/systemd/system ]] || { echo "Requires systemd as the host init system" >&2; exit 5; }

# Do not replace binaries, unit files, or configuration beneath a running service.
# A live upgrade requires its own audited stop/migration/rollback procedure.
for unit in chatgpt-coder.service chatgpt-worker.service; do
  if systemctl is-active --quiet "$unit"; then
    echo "Refusing staged installation while $unit is running; use an audited maintenance procedure." >&2
    exit 10
  fi
done

# Fail closed if the OLD one-user layout is present. Do not silently migrate secrets.
if [[ -e "$CONFIG_DIR/runtime.env" || -d /srv/chatgpt-coder ]]; then
  echo "Legacy single-UID installation detected; manual audit/removal required." >&2
  exit 6
fi

for user in "$CTRL" "$WORKER"; do
  if ! id -u "$user" >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "/srv/$user/home" \
      --shell /usr/sbin/nologin "$user"
  fi
done
if [[ "$(id -u "$CTRL")" == "$(id -u "$WORKER")" ]]; then
  echo "Security violation: controller and worker must have distinct UIDs." >&2
  exit 7
fi

install -d -o "$CTRL" -g "$CTRL" -m 0700 \
  "$CTRL_ROOT" "$CTRL_ROOT/home" "$CTRL_ROOT/home/.config" \
  "$CTRL_ROOT/state" "$CTRL_ROOT/empty"
install -d -o "$WORKER" -g "$WORKER" -m 0700 \
  "$WORKER_ROOT" "$WORKER_ROOT/home" "$WORKER_ROOT/home/.config" \
  "$WORKER_ROOT/state" "$WORKER_ROOT/git" "$WORKER_ROOT/worktrees" \
  "$WORKER_ROOT/skills"
install -d -o root -g root -m 0755 "$OPT_DIR"
install -d -o root -g root -m 0700 "$CONFIG_DIR"

# Pinned public upstream; this is a READ-ONLY clone, never a write to that repo.
if [[ ! -d "$OPT_DIR/source/.git" ]]; then
  git clone --filter=blob:none https://github.com/fwerkor/local-shell-mcp.git "$OPT_DIR/source"
fi
git -C "$OPT_DIR/source" fetch origin "$PIN"
git -C "$OPT_DIR/source" checkout --detach "$PIN"
[[ "$(git -C "$OPT_DIR/source" rev-parse HEAD)" == "$PIN" ]] ||
  { echo "External backend SHA does not match pin" >&2; exit 8; }
if [[ ! -x "$OPT_DIR/venv/bin/python" ]]; then
  python3 -m venv "$OPT_DIR/venv"
fi
"$OPT_DIR/venv/bin/python" -m pip install --disable-pip-version-check "$OPT_DIR/source"
install -o root -g root -m 0755 "$HERE/nondumpable_mcp_entrypoint.py" \
  "$OPT_DIR/nondumpable_mcp_entrypoint.py"

# The ONLY project repository on this worker is Public. No write-enabled push URL.
if [[ ! -d "$WORKER_ROOT/git/Public/.git" ]]; then
  runuser -u "$WORKER" -- git clone --filter=blob:none \
    https://github.com/Binilts03/Public.git "$WORKER_ROOT/git/Public"
fi
if [[ ! -d "$WORKER_ROOT/worktrees/Public" ]]; then
  runuser -u "$WORKER" -- git -C "$WORKER_ROOT/git/Public" \
    worktree add --detach "$WORKER_ROOT/worktrees/Public" HEAD
fi
runuser -u "$WORKER" -- git -C "$WORKER_ROOT/git/Public" \
  remote set-url --push origin no-push://disabled
runuser -u "$WORKER" -- git -C "$WORKER_ROOT/worktrees/Public" \
  config user.name "ChatGPT Workspace Qualifier"
runuser -u "$WORKER" -- git -C "$WORKER_ROOT/worktrees/Public" \
  config user.email "chatgpt-qualifier@example.invalid"

# Controller secrets remain on controller identity only (systemd reads root-owned env).
if [[ ! -e "$CONFIG_DIR/controller.env" ]]; then
  ADMIN_PIN="$(openssl rand -hex 32)"
  JWT_SECRET="$(openssl rand -hex 48)"
  cat > "$CONFIG_DIR/controller.env" <<EOF
LOCAL_SHELL_MCP_MODE=mcp
LOCAL_SHELL_MCP_HOST=127.0.0.1
LOCAL_SHELL_MCP_PORT=8765
LOCAL_SHELL_MCP_WORKSPACE_ROOT=$CTRL_ROOT/empty
LOCAL_SHELL_MCP_STATE_DIR=$CTRL_ROOT/state
LOCAL_SHELL_MCP_DISABLE_LOCAL=true
LOCAL_SHELL_MCP_AUTH_MODE=oauth
LOCAL_SHELL_MCP_AUTH_BYPASS_LOCALHOST=false
LOCAL_SHELL_MCP_REQUIRE_AUTH_FOR_MCP_DISCOVERY=true
LOCAL_SHELL_MCP_OAUTH_ACCESS_TOKEN_TTL_S=86400
LOCAL_SHELL_MCP_PUBLIC_BASE_URL=https://REPLACE-WITH-AUTHORIZED-HOST.invalid
LOCAL_SHELL_MCP_OAUTH_ADMIN_PIN=$ADMIN_PIN
LOCAL_SHELL_MCP_OAUTH_JWT_SECRET=$JWT_SECRET
LOCAL_SHELL_MCP_REMOTE_ENABLED=true
LOCAL_SHELL_MCP_REMOTE_PEER_TRANSFER_ENABLED=false
LOCAL_SHELL_MCP_ALLOW_FULL_CONTAINER=false
LOCAL_SHELL_MCP_UI_ENABLED=false
LOCAL_SHELL_MCP_LIVE_WORKSPACE_ENABLED=false
EOF
fi

# This environment has NO OAuth signing secret and NO access to controller state.
if [[ ! -e "$CONFIG_DIR/worker.env" ]]; then
  cat > "$CONFIG_DIR/worker.env" <<EOF
LOCAL_SHELL_MCP_WORKSPACE_ROOT=$WORKER_ROOT/worktrees/Public
LOCAL_SHELL_MCP_WORKER_STATE_DIR=$WORKER_ROOT/state
LOCAL_SHELL_MCP_STATE_DIR=$WORKER_ROOT/state
LOCAL_SHELL_MCP_AGENT_CONFIG_DIR=$WORKER_ROOT/skills
LOCAL_SHELL_MCP_REMOTE_ENABLED=false
LOCAL_SHELL_MCP_ALLOW_FULL_CONTAINER=false
LOCAL_SHELL_MCP_UI_ENABLED=false
LOCAL_SHELL_MCP_LIVE_WORKSPACE_ENABLED=false
EOF
fi
for env_file in "$CONFIG_DIR/controller.env" "$CONFIG_DIR/worker.env"; do
  chown root:root "$env_file"
  chmod 0600 "$env_file"
done
if grep -Eqi '^(LOCAL_SHELL_MCP_OAUTH_|.*JWT_SECRET=|.*ADMIN_PIN=)' "$CONFIG_DIR/worker.env"; then
  echo "Security violation: worker environment contains controller secrets." >&2
  exit 9
fi

install -o root -g root -m 0644 "$HERE/chatgpt-coder.service" \
  /etc/systemd/system/chatgpt-coder.service
install -o root -g root -m 0644 "$HERE/chatgpt-worker.service" \
  /etc/systemd/system/chatgpt-worker.service
systemctl daemon-reload
systemctl disable chatgpt-worker.service chatgpt-coder.service >/dev/null 2>&1 || true

echo "STAGED: controller UID and worker UID are separate; only Binilts03/Public was cloned."
echo "Both services remain disabled and stopped. No endpoint/tunnel or plugin was created."
echo "HARD STOP: Host isolation, worker enrollment, and plugin account access still require live qualification."
