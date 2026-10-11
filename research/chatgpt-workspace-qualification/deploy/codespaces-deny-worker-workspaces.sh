#!/usr/bin/env bash
# Harden an EXISTING Codespace: forbid ONLY chatgpt-worker from traversing
# /workspaces by adding a named-UID ACL on its parent. Do not alter any child
# checkout, OAuth material, worker enrollment, or public port configuration.
# Usage: sudo bash research/chatgpt-workspace-qualification/deploy/codespaces-deny-worker-workspaces.sh
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo 'Run with sudo bash, never source this script' >&2
  return 2
fi
set -euo pipefail
umask 077

abort() { printf 'BLOCKED: %s\n' "$*" >&2; exit 2; }
WORKER=chatgpt-worker
PARENT=/workspaces
ORIGINAL=/workspaces/Public
RUNTIME=/opt/public-chatgpt-mcp
ATTEST="$RUNTIME/codespaces-isolation-qualified"
SNAPSHOT="$RUNTIME/codespaces-workspaces-parent-acl.before"

[[ "$EUID" == 0 && "${SUDO_USER:-}" == codespace ]] ||
  abort 'must run via sudo bash from the Codespaces owner account'
[[ "$#" == 0 ]] || abort 'no arguments are accepted'
[[ -d "$PARENT" && ! -L "$PARENT" && -d "$ORIGINAL" && ! -L "$ORIGINAL" ]] ||
  abort 'unexpected /workspaces filesystem layout'
[[ "$(stat -c '%U' "$ORIGINAL")" == codespace ]] ||
  abort 'original Public checkout owner differs from codespace'
[[ -d "$RUNTIME" && "$(stat -c '%U' "$RUNTIME")" == root ]] ||
  abort 'staged root-owned MCP runtime missing'
[[ -f "$ATTEST" && "$(stat -c '%U:%a' "$ATTEST")" == root:600 ]] ||
  abort 'prior Stage 2 isolation qualification missing'
for executable in getfacl setfacl runuser stat git pgrep; do
  command -v "$executable" >/dev/null || abort "missing prerequisite $executable"
done
id "$WORKER" >/dev/null 2>&1 || abort 'worker identity not found'
[[ "$(id -u "$WORKER")" != 0 ]] || abort 'worker identity cannot be root'
if pgrep -u "$WORKER" >/dev/null 2>&1; then
  abort 'worker processes already running; refuse ACL changes on live execution host'
fi
runuser -u codespace -- test -r "$ORIGINAL" || abort 'Codespaces owner cannot read Public before change'
runuser -u codespace -- test -w "$ORIGINAL" || abort 'Codespaces owner cannot write Public before change'
[[ -z "$(runuser -u codespace -- git -C "$ORIGINAL" status --porcelain)" ]] ||
  abort 'original Codespaces Git worktree is not clean'
remote="$(runuser -u codespace -- git -C "$ORIGINAL" remote get-url origin)"
case "$remote" in
  https://github.com/Binilts03/Public|https://github.com/Binilts03/Public.git|git@github.com:Binilts03/Public.git) ;;
  *) abort 'unexpected Git origin; Public only';;
esac
[[ "$(runuser -u codespace -- git -C "$ORIGINAL" branch --show-current)" ==
   experiments/chatgpt-workspace-qualification ]] || abort 'wrong qualification branch'
runuser -u "$WORKER" -- test ! -x "$ORIGINAL" ||
  abort 'existing Public ACL must already deny worker traversal'
runuser -u "$WORKER" -- test ! -r /srv/chatgpt-controller/controller.env ||
  abort 'worker can read controller OAuth credentials'
runuser -u "$WORKER" -- test -x /srv/chatgpt-worker/worktrees/Public ||
  abort 'worker cannot traverse its authorized /srv worktree'

before_owner="$(stat -c '%u:%g' "$PARENT")"
already_denied=false
if runuser -u "$WORKER" -- test ! -x "$PARENT" &&
   runuser -u "$WORKER" -- test ! -w "$PARENT"; then
  already_denied=true
fi
if [[ "$already_denied" == false ]]; then
  [[ ! -e "$SNAPSHOT" ]] || abort 'ACL snapshot already exists; refusing to overwrite evidence'
  getfacl -p "$PARENT" > "$SNAPSHOT" || abort 'cannot snapshot /workspaces ACL'
  chown root:root "$SNAPSHOT"
  chmod 0600 "$SNAPSHOT"
  # -n preserves any existing ACL mask rather than recalculating it.
  # Only modify the named worker UID entry on the PARENT, never child paths.
  setfacl -n -m "u:$WORKER:---" "$PARENT" ||
    abort 'parent filesystem does not support an effective named worker-deny ACL'
  echo 'PARENT_WORKSPACE_ACL_REPAIR_APPLIED: named-worker deny on /workspaces only'
else
  echo 'PARENT_WORKSPACE_ACL_ALREADY_DENIED: no ACL modification required'
fi

[[ "$(stat -c '%u:%g' "$PARENT")" == "$before_owner" ]] ||
  abort 'parent owner unexpectedly changed'
runuser -u "$WORKER" -- test ! -x "$PARENT" ||
  abort 'worker can still traverse /workspaces parent'
runuser -u "$WORKER" -- test ! -w "$PARENT" ||
  abort 'worker can still write /workspaces parent'
runuser -u "$WORKER" -- test ! -x "$ORIGINAL" ||
  abort 'worker can still traverse Public checkout'
runuser -u "$WORKER" -- test ! -w "$ORIGINAL" ||
  abort 'worker can still write Public checkout'
runuser -u "$WORKER" -- test ! -r "$ORIGINAL/.git/config" ||
  abort 'worker can still read original Git config'
runuser -u codespace -- test -x "$PARENT" ||
  abort 'Codespaces owner cannot traverse /workspaces after targeted ACL'
runuser -u codespace -- test -w "$ORIGINAL" ||
  abort 'Codespaces owner cannot write Public after targeted ACL'
[[ -z "$(runuser -u codespace -- git -C "$ORIGINAL" status --porcelain)" ]] ||
  abort 'original Public Git worktree was modified'
for other in /workspaces/* /workspaces/.[!.]* /workspaces/..?*; do
  [[ -e "$other" && "$other" != "$ORIGINAL" ]] || continue
  [[ -d "$other" ]] || continue
  runuser -u "$WORKER" -- test ! -x "$other" ||
    abort 'worker can still traverse another immediate workspace entry'
  runuser -u "$WORKER" -- test ! -w "$other" ||
    abort 'worker can still write another immediate workspace entry'
done
for socket in /run/docker.sock /var/run/docker.sock; do
  [[ -e "$socket" ]] || continue
  runuser -u "$WORKER" -- test ! -r "$socket" ||
    abort 'worker can read Docker socket'
  runuser -u "$WORKER" -- test ! -w "$socket" ||
    abort 'worker can write Docker socket'
done
echo 'PARENT_WORKSPACE_ISOLATION_PASS: worker blocked from all /workspaces entries; owner can still access Public'
echo 'NO_SIBLING_REPO_MUTATIONS_NO_SECRETS_CHANGED_NO_WORKER_ENROLLED_NO_PORT_CHANGES'
