#!/usr/bin/env bash
# Prepare a Codespaces controller and worker under distinct Linux UIDs.
# Does not start a daemon, enroll a worker, publish a port or install a plugin.
# Run: sudo bash research/chatgpt-workspace-qualification/deploy/codespaces-isolated-stage.sh
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "Run with sudo bash, never source this file" >&2
  return 2
fi
set -euo pipefail
umask 077
abort() { printf 'BLOCKED: %s\n' "$*" >&2; exit 2; }

REPO=/workspaces/Public
EXPECTED=experiments/chatgpt-workspace-qualification
PIN=dec01b9f50f966097ddfc84d357d12a52f238935
CUSER=codespace
CTRL=chatgpt-controller
WORKER=chatgpt-worker
SRC=/home/codespace/.local/share/public-chatgpt-mcp-stage/local-shell-mcp
# System-owned Python 3.12 is the CI-tested major/minor runtime.
# Avoid executing a Codespace-owned uv binary as root.
SYSTEM_PY=/usr/bin/python3
RUNTIME=/opt/public-chatgpt-mcp
CTRL_ROOT=/srv/chatgpt-controller
WORKER_ROOT=/srv/chatgpt-worker

[[ "$EUID" == 0 ]] || abort "requires sudo bash"
[[ "${SUDO_USER:-}" == "$CUSER" ]] || abort "must be launched by the codespace login via sudo"
[[ -d "$REPO" ]] || abort "missing repository directory: $REPO"
[[ -d "$SRC/.git" ]] || abort "missing pinned backend checkout at $SRC; the Stage 1 source was not found"
# The Stage 1 uv install proved local MCP compatibility; this root installer
# must NOT execute the Codespace user's uv, Python, or pipx as root.
[[ -x "$SYSTEM_PY" ]] || abort "system Python missing at $SYSTEM_PY"
if ! "$SYSTEM_PY" -c 'import sys; assert sys.version_info[:2] == (3,12)' 2>/dev/null; then
  abort "$SYSTEM_PY is not Python 3.12; stop before creating system users"
fi
# Test ensurepip/venv before any persistent mutations so a missing
# python3.12-venv package cannot leave a half-installed privileged layout.
probe="$(mktemp -d /tmp/public-mcp-venv-check.XXXXXXXX)"
if ! "$SYSTEM_PY" -m venv "$probe" >/dev/null 2>&1; then
  rm -rf -- "$probe"
  abort "system Python 3.12 venv is unavailable; check python3.12-venv before installation"
fi
"$probe/bin/python" -m pip --version >/dev/null ||
  { rm -rf -- "$probe"; abort "system Python virtualenv has no pip"; }
rm -rf -- "$probe"
printf 'Prerequisites: pinned source present, system-owned Python %s and venv/pip available\n' "$("$SYSTEM_PY" --version 2>&1)"
[[ ! -d /run/systemd/system ]] || abort "dedicated VM installer must be used on systemd hosts"
for executable in useradd runuser install git openssl; do
  command -v "$executable" >/dev/null || abort "missing $executable"
done
gitu() { runuser -u "$CUSER" -- git -C "$REPO" "$@"; }
case "$(gitu remote get-url origin)" in
  https://github.com/Binilts03/Public|https://github.com/Binilts03/Public.git|git@github.com:Binilts03/Public.git) ;;
  *) abort "only Binilts03/Public may be used";;
esac
[[ "$(gitu branch --show-current)" == "$EXPECTED" ]] || abort "wrong qualification branch"
[[ -z "$(gitu status --porcelain)" ]] || abort "dirty workspace; no reset or overwrite performed"
[[ "$(runuser -u "$CUSER" -- git -C "$SRC" rev-parse HEAD)" == "$PIN" ]] ||
  abort "upstream backend SHA mismatch"
[[ -z "$(runuser -u "$CUSER" -- git -C "$SRC" status --porcelain)" ]] ||
  abort "backend source modified"
[[ ! -e "$RUNTIME" && ! -e "$CTRL_ROOT" && ! -e "$WORKER_ROOT" ]] ||
  abort "an installation already exists; refusing to modify live or partial state"

printf '%s\n' '1/5 Creating isolated system users (no supplementary groups)'
for account in "$CTRL" "$WORKER"; do
  if id "$account" >/dev/null 2>&1; then
    abort "$account already exists; review it before proceeding"
  fi
done
useradd --system --user-group --home-dir "$CTRL_ROOT/home" --shell /usr/sbin/nologin "$CTRL"
useradd --system --user-group --home-dir "$WORKER_ROOT/home" --shell /usr/sbin/nologin "$WORKER"
[[ "$(id -u "$CTRL")" != "$(id -u "$WORKER")" ]] || abort "UID separation failed"
for account in "$CTRL" "$WORKER"; do
  for group in docker sudo ssh; do
    if id -nG "$account" | tr ' ' '\n' | grep -qx "$group"; then
      abort "$account has forbidden $group membership"
    fi
  done
done

printf '%s\n' '2/5 Installing root-owned runtime from pinned upstream source'
install -d -o root -g root -m 0755 "$RUNTIME"
cp -a "$SRC" "$RUNTIME/source"
chown -R root:root "$RUNTIME/source"
[[ "$(git -C "$RUNTIME/source" rev-parse HEAD)" == "$PIN" ]] || abort "copied pin mismatch"
# The app runtime is public-code, not credential state. Use standard read
# permissions for both restricted Linux identities. Keep the top-level installer
# umask 077 for all OAuth env/state files created later.
(
  umask 022
  "$SYSTEM_PY" -m venv "$RUNTIME/venv"
  "$RUNTIME/venv/bin/python" -m pip install --disable-pip-version-check "$RUNTIME/source"
)
"$RUNTIME/venv/bin/python" -c 'import sys,local_shell_mcp; assert sys.version_info[:2]==(3,12)'
runuser -u "$CTRL" -- "$RUNTIME/venv/bin/python" -c 'import local_shell_mcp.main' ||
  abort "controller cannot import staged root-owned Python runtime"
runuser -u "$WORKER" -- "$RUNTIME/venv/bin/python" -c 'import local_shell_mcp.remote_worker' ||
  abort "worker cannot import staged root-owned Python runtime"
install -o root -g root -m 0755 \
  "$REPO/research/chatgpt-workspace-qualification/deploy/nondumpable_mcp_entrypoint.py" \
  "$RUNTIME/nondumpable_mcp_entrypoint.py"

printf '%s\n' '3/5 Creating separate 0700 process state directories'
install -d -o "$CTRL" -g "$CTRL" -m 0700 \
  "$CTRL_ROOT" "$CTRL_ROOT/home" "$CTRL_ROOT/home/.config" "$CTRL_ROOT/state" \
  "$CTRL_ROOT/empty" "$CTRL_ROOT/logs"
install -d -o "$WORKER" -g "$WORKER" -m 0700 \
  "$WORKER_ROOT" "$WORKER_ROOT/home" "$WORKER_ROOT/home/.config" \
  "$WORKER_ROOT/state" "$WORKER_ROOT/git" "$WORKER_ROOT/worktrees" \
  "$WORKER_ROOT/skills" "$WORKER_ROOT/logs"

printf '%s\n' '4/5 Cloning only Public as worker with no Git credentials or push URL'
worker_git() {
  runuser -u "$WORKER" -- env -i HOME="$WORKER_ROOT/home" PATH=/usr/bin:/bin \
    GIT_TERMINAL_PROMPT=0 git -c credential.helper= "$@"
}
worker_git clone --filter=blob:none https://github.com/Binilts03/Public.git "$WORKER_ROOT/git/Public"
worker_git -C "$WORKER_ROOT/git/Public" fetch origin "$EXPECTED"
BASE="$(worker_git -C "$WORKER_ROOT/git/Public" rev-parse "origin/$EXPECTED")"
worker_git -C "$WORKER_ROOT/git/Public" worktree add --detach "$WORKER_ROOT/worktrees/Public" "$BASE"
worker_git -C "$WORKER_ROOT/git/Public" remote set-url --push origin no-push://disabled
worker_git -C "$WORKER_ROOT/worktrees/Public" config user.name 'ChatGPT Workspace Qualifier'
worker_git -C "$WORKER_ROOT/worktrees/Public" config user.email 'chatgpt-qualifier@example.invalid'
[[ "$(worker_git -C "$WORKER_ROOT/git/Public" remote get-url --push origin)" == no-push://disabled ]] ||
  abort "push is not disabled"

printf '%s\n' '5/5 Generating controller-only OAuth configuration (not activated)'
ADMIN_PIN="$(openssl rand -hex 32)"
JWT_SECRET="$(openssl rand -hex 48)"
cat > "$CTRL_ROOT/controller.env" <<EOF
LOCAL_SHELL_MCP_MODE=mcp
LOCAL_SHELL_MCP_HOST=127.0.0.1
LOCAL_SHELL_MCP_PORT=8765
LOCAL_SHELL_MCP_WORKSPACE_ROOT=$CTRL_ROOT/empty
LOCAL_SHELL_MCP_STATE_DIR=$CTRL_ROOT/state
LOCAL_SHELL_MCP_DISABLE_LOCAL=true
LOCAL_SHELL_MCP_AUTH_MODE=oauth
LOCAL_SHELL_MCP_AUTH_BYPASS_LOCALHOST=false
LOCAL_SHELL_MCP_REQUIRE_AUTH_FOR_MCP_DISCOVERY=true
LOCAL_SHELL_MCP_OAUTH_ACCESS_TOKEN_TTL_S=3600
LOCAL_SHELL_MCP_PUBLIC_BASE_URL=https://REPLACE-WITH-AUTHORIZED-HOST.invalid
LOCAL_SHELL_MCP_OAUTH_ADMIN_PIN=$ADMIN_PIN
LOCAL_SHELL_MCP_OAUTH_JWT_SECRET=$JWT_SECRET
LOCAL_SHELL_MCP_REMOTE_ENABLED=true
LOCAL_SHELL_MCP_REMOTE_PEER_TRANSFER_ENABLED=false
LOCAL_SHELL_MCP_ALLOW_FULL_CONTAINER=false
LOCAL_SHELL_MCP_UI_ENABLED=false
LOCAL_SHELL_MCP_LIVE_WORKSPACE_ENABLED=false
EOF
install -o "$CTRL" -g "$CTRL" -m 0600 "$CTRL_ROOT/controller.env" "$CTRL_ROOT/controller.env.secure"
mv -f "$CTRL_ROOT/controller.env.secure" "$CTRL_ROOT/controller.env"
cat > "$WORKER_ROOT/worker.env" <<EOF
LOCAL_SHELL_MCP_WORKSPACE_ROOT=$WORKER_ROOT/worktrees/Public
LOCAL_SHELL_MCP_WORKER_STATE_DIR=$WORKER_ROOT/state
LOCAL_SHELL_MCP_STATE_DIR=$WORKER_ROOT/state
LOCAL_SHELL_MCP_AGENT_CONFIG_DIR=$WORKER_ROOT/skills
LOCAL_SHELL_MCP_REMOTE_ENABLED=false
LOCAL_SHELL_MCP_ALLOW_FULL_CONTAINER=false
LOCAL_SHELL_MCP_UI_ENABLED=false
LOCAL_SHELL_MCP_LIVE_WORKSPACE_ENABLED=false
EOF
chown "$WORKER:$WORKER" "$WORKER_ROOT/worker.env"
chmod 0600 "$WORKER_ROOT/worker.env"
runuser -u "$WORKER" -- test ! -r "$CTRL_ROOT/controller.env" ||
  abort "worker can read controller OAuth configuration"
runuser -u "$CTRL" -- test ! -r "$WORKER_ROOT/worker.env" ||
  abort "controller can read worker state"
runuser -u "$WORKER" -- test ! -w "$REPO" ||
  abort "worker can write to the original Codespaces worktree"
for protected in /home/codespace/.config/gh/hosts.yml /home/codespace/.git-credentials /home/codespace/.ssh/id_ed25519; do
  if [[ -e "$protected" ]]; then
    runuser -u "$WORKER" -- test ! -r "$protected" ||
      abort "worker can read Codespaces private account material"
  fi
done
for socket in /var/run/docker.sock /run/docker.sock; do
  if [[ -e "$socket" ]]; then
    runuser -u "$WORKER" -- test ! -r "$socket" ||
      abort "worker can access Docker socket"
  fi
done
grep -q '^LOCAL_SHELL_MCP_DISABLE_LOCAL=true$' "$CTRL_ROOT/controller.env"
echo "ISOLATION_STAGED_PASS controller and worker distinct, Public only, no push, OAuth private."
echo "HOST_NOT_EXPOSED no listeners started; no worker enrolled; no plugin connected."
echo "WORKTREE_BASE=$BASE"
