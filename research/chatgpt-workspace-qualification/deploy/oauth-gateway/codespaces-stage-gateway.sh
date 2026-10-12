#!/usr/bin/env bash
# One-time gateway UID+ACL+code staging only. NO network ingress or processes.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo 'BLOCKED: run via sudo bash; do not source' >&2
  return 2
fi
set -euo pipefail
umask 077
abort() { printf 'BLOCKED: %s\n' "$*" >&2; exit 2; }

OWNER=codespace
ORIGINAL=/workspaces/Public
PARENT=/workspaces
EVIDENCE=/opt/public-chatgpt-mcp/codespaces-isolation-qualified
GATE=chatgpt-oauth-gateway
STAGE=/opt/public-chatgpt-oauth-gateway
STATE=/srv/chatgpt-oauth-gateway
SOURCE="$ORIGINAL/research/chatgpt-workspace-qualification/deploy/oauth-gateway/gateway.py"

[[ "$EUID" == 0 && "${SUDO_USER:-}" == "$OWNER" ]] ||
  abort 'requires sudo from the Codespaces owner account'
[[ "$#" == 1 && "$1" == "--stage-only" ]] ||
  abort 'explicit --stage-only required; no other actions accepted'
for cmd in useradd runuser install getfacl setfacl git stat sha256sum; do
  command -v "$cmd" >/dev/null 2>&1 || abort "missing prerequisite $cmd"
done
[[ -d "$PARENT" && ! -L "$PARENT" && -d "$ORIGINAL" && ! -L "$ORIGINAL" ]] ||
  abort 'unexpected Codespaces workspace layout'
[[ "$(stat -c %U "$ORIGINAL")" == "$OWNER" ]] ||
  abort 'unexpected Public checkout owner'
[[ -f "$EVIDENCE" && ! -L "$EVIDENCE" &&
   "$(stat -c '%U:%a' "$EVIDENCE")" == root:600 ]] ||
  abort 'original controller/worker isolation evidence missing'
[[ -f "$SOURCE" && ! -L "$SOURCE" ]] || abort 'gateway source absent or symlink'
for account in chatgpt-controller chatgpt-worker chatgpt-tunnel; do
  id "$account" >/dev/null 2>&1 || abort "existing separate UID $account absent"
done
[[ ! -e "$STAGE" && ! -L "$STAGE" && ! -e "$STATE" && ! -L "$STATE" ]] ||
  abort 'gateway staging state already exists; refuse to overwrite'
if id "$GATE" >/dev/null 2>&1; then
  abort 'gateway UID already exists; reconcile before staging'
fi
origin="$(runuser -u "$OWNER" -- git -C "$ORIGINAL" remote get-url origin)"
case "$origin" in
  https://github.com/Binilts03/Public|https://github.com/Binilts03/Public.git|git@github.com:Binilts03/Public.git) ;;
  *) abort 'only Public repository authorized';;
esac
[[ "$(runuser -u "$OWNER" -- git -C "$ORIGINAL" branch --show-current)" ==
   experiments/chatgpt-workspace-qualification ]] ||
  abort 'wrong qualification branch'
[[ -z "$(runuser -u "$OWNER" -- git -C "$ORIGINAL" status --porcelain)" ]] ||
  abort 'uncommitted modifications; refuse stage'
runuser -u "$OWNER" -- test -w "$ORIGINAL" ||
  abort 'Codespaces owner cannot write Public before ACL change'
[[ ! -e /run/systemd/system ]] ||
  abort 'Codespaces staging is not intended for managed systemd VM'

# Save existing ACL before one narrowly targeted new named-UID deny entry.
install -d -o root -g root -m 0700 "$STATE"
getfacl -p "$PARENT" > "$STATE/workspaces-parent-acl.before"
chown root:root "$STATE/workspaces-parent-acl.before"
chmod 0600 "$STATE/workspaces-parent-acl.before"

useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$GATE"
[[ "$(id -u "$GATE")" != 0 ]] || abort 'gateway cannot run as root'
for group in root sudo docker ssh codespace; do
  if id -nG "$GATE" | tr ' ' '\n' | grep -qx "$group"; then
    abort "gateway has forbidden supplementary group $group"
  fi
done
prior_parent="$(stat -c '%u:%g' "$PARENT")"
setfacl -n -m "u:$GATE:---" "$PARENT" ||
  abort 'named-UID ACL unavailable on /workspaces'
[[ "$(stat -c '%u:%g' "$PARENT")" == "$prior_parent" ]] ||
  abort 'workspace parent ownership changed'
runuser -u "$GATE" -- test ! -x "$PARENT" ||
  abort 'gateway can traverse /workspaces'
runuser -u "$GATE" -- test ! -x "$ORIGINAL" ||
  abort 'gateway can traverse original Public'
runuser -u "$GATE" -- test ! -r "$ORIGINAL/.git/config" ||
  abort 'gateway can read original Git config'
for other in /workspaces/* /workspaces/.[!.]* /workspaces/..?*; do
  [[ -e "$other" && "$other" != "$ORIGINAL" ]] || continue
  runuser -u "$GATE" -- test ! -x "$other" ||
    abort 'gateway can traverse sibling workspaces'
done
runuser -u "$OWNER" -- test -w "$ORIGINAL" ||
  abort 'Codespaces owner lost Public access'
runuser -u "$GATE" -- test ! -r /srv/chatgpt-controller/controller.env ||
  abort 'gateway can read controller OAuth secrets'
runuser -u "$GATE" -- test ! -x /srv/chatgpt-worker/worktrees/Public ||
  abort 'gateway can traverse remote worker worktree'
for sock in /run/docker.sock /var/run/docker.sock; do
  [[ -e "$sock" ]] || continue
  runuser -u "$GATE" -- test ! -r "$sock" ||
    abort 'gateway can read Docker socket'
  runuser -u "$GATE" -- test ! -w "$sock" ||
    abort 'gateway can write Docker socket'
done

install -d -o root -g root -m 0755 "$STAGE"
install -o root -g root -m 0644 "$SOURCE" "$STAGE/gateway.py"
[[ "$(sha256sum "$SOURCE" | cut -d ' ' -f 1)" ==
   "$(sha256sum "$STAGE/gateway.py" | cut -d ' ' -f 1)" ]] ||
  abort 'gateway source digest mismatch after installation'
runuser -u "$GATE" -- env -i PATH=/usr/bin:/bin HOME=/nonexistent \
  PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "$STAGE/gateway.py" --help >/dev/null ||
  abort 'gateway identity cannot load root-owned staged code'
[[ -z "$(runuser -u "$OWNER" -- git -C "$ORIGINAL" status --porcelain)" ]] ||
  abort 'Public worktree unexpectedly changed'
echo 'OAUTH_GATEWAY_UID_AND_PARENT_ACL_STAGE_PASS'
echo 'GATEWAY_CODE_ROOT_OWNED_NO_SERVICE_STARTED'
echo 'NO_PUBLIC_PORT_NO_CONTROLLER_RESTART_NO_WORKER_CHANGE_NO_GIT_WRITE'
