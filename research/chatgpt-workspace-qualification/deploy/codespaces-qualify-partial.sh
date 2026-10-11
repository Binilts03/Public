#!/usr/bin/env bash
# Recover Stage 2 after the genuine Codespaces worktree-access denial.
# Run exactly once as needed, from the owner login with sudo bash.
# NO deletion, recloning, secret rotation, service start or public ingress.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo 'Run with sudo bash, never source this script' >&2
  return 2
fi
set -euo pipefail
umask 077
abort() { printf 'BLOCKED: %s\n' "$*" >&2; exit 2; }

REPO=/workspaces/Public
WORKER=chatgpt-worker
CTRL=chatgpt-controller
WORKER_ROOT=/srv/chatgpt-worker
CTRL_ROOT=/srv/chatgpt-controller
RUNTIME=/opt/public-chatgpt-mcp
PIN=dec01b9f50f966097ddfc84d357d12a52f238935
BRANCH=experiments/chatgpt-workspace-qualification
ALLOW_REMOTE=https://github.com/Binilts03/Public.git
QUALIFIED="$RUNTIME/codespaces-isolation-qualified"

[[ "$EUID" == 0 && "${SUDO_USER:-}" == codespace ]] || abort 'run via sudo bash from codespace user'
[[ $# -eq 0 ]] || abort 'no positional parameters accepted'
[[ ! -L "$REPO" && -d "$REPO" ]] || abort 'Codespaces Public must be a real directory, not a symlink'
[[ "$(stat -c '%U' "$REPO")" == codespace ]] || abort 'Codespaces Public directory owner is not codespace'
[[ ! -d /run/systemd/system ]] || abort 'not a non-systemd Codespace'
for bin in git runuser stat getfacl setfacl; do
  command -v "$bin" >/dev/null || abort "missing $bin (install package 'acl' if setfacl/getfacl missing)"
done
for user in "$CTRL" "$WORKER"; do
  id "$user" >/dev/null 2>&1 || abort "missing existing system user $user; do not rerun original installer"
  [[ "$(id -u "$user")" -ne 0 ]] || abort "invalid root identity $user"
  for group in docker sudo ssh; do
    if id -nG "$user" | tr ' ' '\n' | grep -qx "$group"; then abort "$user belongs to forbidden group $group"; fi
  done
done
[[ "$(id -u "$CTRL")" != "$(id -u "$WORKER")" ]] || abort 'controller and worker UIDs must differ'
[[ ! -e "$QUALIFIED" ]] || abort 'prior qualification marker already exists; inspect before repeating'
if pgrep -u "$CTRL" >/dev/null 2>&1 || pgrep -u "$WORKER" >/dev/null 2>&1; then
  abort 'controller or worker process is already running; refuse live mutation'
fi
if command -v ss >/dev/null 2>&1 && ss -ltn | grep -Eq '(:8765)[[:space:]]'; then
  abort 'TCP port 8765 already has a listener'
fi

as_codespace() { runuser -u codespace -- git -C "$REPO" "$@"; }
case "$(as_codespace remote get-url origin)" in
  https://github.com/Binilts03/Public|https://github.com/Binilts03/Public.git|git@github.com:Binilts03/Public.git) ;;
  *) abort 'original Codespaces Git remote is not Public';;
esac
[[ "$(as_codespace branch --show-current)" == "$BRANCH" ]] || abort 'wrong original Git branch'
[[ -z "$(as_codespace status --porcelain)" ]] || abort 'original Codespaces checkout is dirty; no mutation permitted'
[[ -x "$RUNTIME/venv/bin/python" && -d "$RUNTIME/source/.git" ]] || abort 'pinned privileged Python/source not staged'
[[ "$(stat -c '%U' "$RUNTIME/source")" == root ]] || abort 'pinned runtime source must be root-owned'
[[ "$(git -C "$RUNTIME/source" rev-parse HEAD)" == "$PIN" ]] || abort 'upstream pinned SHA mismatch'
"$RUNTIME/venv/bin/python" -c 'import sys,local_shell_mcp; assert sys.version_info[:2]==(3,12)' || abort 'privileged MCP runtime invalid'
for item in "$CTRL_ROOT" "$CTRL_ROOT/state" "$WORKER_ROOT" "$WORKER_ROOT/state"; do
  [[ -d "$item" ]] || abort "missing prior staging directory $item"
done
[[ "$(stat -c '%U:%a' "$CTRL_ROOT/state")" == "$CTRL:700" ]] || abort 'controller state owner or mode is unsafe'
[[ "$(stat -c '%U:%a' "$WORKER_ROOT/state")" == "$WORKER:700" ]] || abort 'worker state owner or mode is unsafe'
[[ "$(stat -c '%U:%a' "$CTRL_ROOT/controller.env")" == "$CTRL:600" ]] || abort 'controller OAuth file owner or mode is unsafe'
[[ "$(stat -c '%U:%a' "$WORKER_ROOT/worker.env")" == "$WORKER:600" ]] || abort 'worker config owner or mode is unsafe'
grep -qx 'LOCAL_SHELL_MCP_DISABLE_LOCAL=true' "$CTRL_ROOT/controller.env" || abort 'local execution is not disabled'
grep -qx 'LOCAL_SHELL_MCP_AUTH_MODE=oauth' "$CTRL_ROOT/controller.env" || abort 'OAuth required'
grep -qx 'LOCAL_SHELL_MCP_AUTH_BYPASS_LOCALHOST=false' "$CTRL_ROOT/controller.env" || abort 'local OAuth bypass forbidden'
grep -qx 'LOCAL_SHELL_MCP_REMOTE_ENABLED=true' "$CTRL_ROOT/controller.env" || abort 'remote worker mode required'
grep -q '^LOCAL_SHELL_MCP_OAUTH_JWT_SECRET=.' "$CTRL_ROOT/controller.env" || abort 'controller JWT secret not provisioned'
if grep -Eq '^LOCAL_SHELL_MCP_OAUTH_(JWT_SECRET|ADMIN_PIN)=' "$WORKER_ROOT/worker.env"; then abort 'worker config contains controller credentials'; fi

worker_git() {
  runuser -u "$WORKER" -- env -i HOME="$WORKER_ROOT/home" PATH=/usr/bin:/bin GIT_TERMINAL_PROMPT=0 git -c credential.helper= "$@"
}
[[ "$(worker_git -C "$WORKER_ROOT/git/Public" remote get-url origin)" == "$ALLOW_REMOTE" ]] || abort 'worker remote not Public'
[[ "$(worker_git -C "$WORKER_ROOT/git/Public" remote get-url --push origin)" == 'no-push://disabled' ]] || abort 'worker Git push is not disabled'
[[ "$(worker_git -C "$WORKER_ROOT/worktrees/Public" rev-parse --is-inside-work-tree)" == true ]] || abort 'worker worktree not present'
[[ -z "$(worker_git -C "$WORKER_ROOT/worktrees/Public" status --porcelain)" ]] || abort 'worker worktree is dirty'

printf '%s\n' 'Preflight PASS: existing staged artifacts, OAuth credentials, Git worktree, runtime and Linux users verified.'
if runuser -u "$WORKER" -- test -x "$REPO" || runuser -u "$WORKER" -- test -w "$REPO"; then
  # Deny the worker named-UID traversal without changing ownership/mode
  # or the files inside the original Codespaces checkout.
  backup="$RUNTIME/codespaces-public-acl-before-repair.txt"
  [[ ! -e "$backup" ]] || abort 'previous ACL snapshot exists; do not overwrite it'
  getfacl -p "$REPO" > "$backup" || abort 'unable to save original ACL'
  chmod 0600 "$backup"
  chown root:root "$backup"
  if ! setfacl -m "u:$WORKER:---" "$REPO"; then
    abort 'filesystem rejected worker-deny ACL; original checkout must not be exposed'
  fi
  echo 'ACL_REPAIR_APPLIED: denied worker traversal to /workspaces/Public; original ACL saved as root-only snapshot.'
else
  echo 'ACL_ALREADY_DENIED: no change to original Codespaces permissions needed.'
fi

runuser -u "$WORKER" -- test ! -x "$REPO" || abort 'worker can still traverse original Public checkout'
runuser -u "$WORKER" -- test ! -w "$REPO" || abort 'worker can still write original Public checkout'
runuser -u "$WORKER" -- test ! -r "$REPO/.git/config" || abort 'worker can still read original Public Git config'
runuser -u codespace -- test -x "$REPO" || abort 'operator Codespace traversal broken'
runuser -u codespace -- test -w "$REPO" || abort 'operator Codespace write access broken'
[[ -z "$(as_codespace status --porcelain)" ]] || abort 'Codespaces original Git worktree was modified'
runuser -u "$WORKER" -- test ! -r "$CTRL_ROOT/controller.env" || abort 'worker can read OAuth credential file'
runuser -u "$WORKER" -- test ! -r "$CTRL_ROOT/state" || abort 'worker can read OAuth state'
runuser -u "$CTRL" -- test ! -r "$WORKER_ROOT/worker.env" || abort 'controller can read worker configuration'
for protected in /home/codespace/.config/gh/hosts.yml /home/codespace/.git-credentials /home/codespace/.ssh/id_ed25519; do
  if [[ -e "$protected" ]]; then
    runuser -u "$WORKER" -- test ! -r "$protected" || abort "worker can read Codespaces credential location $protected"
  fi
done
for socket in /var/run/docker.sock /run/docker.sock; do
  if [[ -e "$socket" ]]; then
    runuser -u "$WORKER" -- test ! -r "$socket" || abort "worker can access privileged Docker socket $socket"
    runuser -u "$WORKER" -- test ! -w "$socket" || abort "worker can write to privileged Docker socket $socket"
  fi
done
# Do not let this worker run if other mounted workspace directories are writable.
for other in /workspaces/*; do
  [[ -d "$other" && "$other" != "$REPO" ]] || continue
  if runuser -u "$WORKER" -- test -w "$other"; then
    abort "worker can write another workspace path: $other"
  fi
done
printf 'schema=codespaces-isolation-stage2/v1\nrepo=Binilts03/Public\nbranch=%s\nupstream_sha=%s\n' "$BRANCH" "$PIN" > "$QUALIFIED"
chown root:root "$QUALIFIED"
chmod 0600 "$QUALIFIED"
echo 'PARTIAL_STAGE_RECOVERED_PASS: worker denied original checkout, controller secrets and Docker socket.'
echo 'HOST_NOT_EXPOSED: no service was started and no port was made public.'
