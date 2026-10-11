#!/usr/bin/env bash
# Read-only Codespaces environment preflight. Run as:
#   bash research/chatgpt-workspace-qualification/deploy/codespaces-preflight.sh
# Intentionally no set -e: optional commands may be missing and must not kill
# an interactive Codespaces terminal. Never source this script.
set +e
ROOT=/workspaces/Public
EXPECTED_BRANCH=experiments/chatgpt-workspace-qualification

printf '%s\n' '=== Codespaces MCP qualification: read-only environment check ==='
if [[ ! -d "$ROOT/.git" ]] && ! git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  printf '%s\n' 'BLOCKED: /workspaces/Public is not a Git worktree'
  exit 0
fi
remote="$(git -C "$ROOT" remote get-url origin 2>/dev/null)"
branch="$(git -C "$ROOT" branch --show-current 2>/dev/null)"
printf 'origin: %s\nbranch: %s\n' "$remote" "$branch"
if [[ "$remote" != 'https://github.com/Binilts03/Public' && "$remote" != 'https://github.com/Binilts03/Public.git' && "$remote" != 'git@github.com:Binilts03/Public.git' ]]; then
  printf '%s\n' 'BLOCKED: origin is not the allowed Public repository; do not deploy'
fi
if [[ "$branch" != "$EXPECTED_BRANCH" ]]; then
  printf '%s\n' 'BLOCKED: qualification branch is not checked out; do not deploy'
fi
printf 'HEAD: %s\n' "$(git -C "$ROOT" rev-parse --short=12 HEAD 2>/dev/null)"
if [[ -n "$(git -C "$ROOT" status --porcelain 2>/dev/null)" ]]; then
  printf '%s\n' 'NOTE: worktree is not clean. No reset, checkout, or pull was performed.'
else
  printf '%s\n' 'worktree: clean'
fi
printf '\n%s\n' '=== Identity and available runtimes ==='
id
python3 --version 2>&1
if command -v uv >/dev/null 2>&1; then
  uv --version
  uv python find 3.12 2>&1 || printf '%s\n' 'NOTE: Python 3.12 is not yet available to uv'
else
  printf '%s\n' 'NOTE: uv is missing (not a shell failure)'
fi
for command in sudo unshare systemctl git openssl; do
  if command -v "$command" >/dev/null 2>&1; then
    printf '%s: present\n' "$command"
  else
    printf '%s: missing\n' "$command"
  fi
done
if [[ -d /run/systemd/system ]]; then
  printf '%s\n' 'systemd: active'
else
  printf '%s\n' 'systemd: not active (do not run the VM-only staged installer)'
fi
if id -nG | grep -Eq '(^|[[:space:]])docker([[:space:]]|$)'; then
  printf '%s\n' 'SECURITY: current user is in docker group; do not run MCP worker under this identity'
fi
printf '\n%s\n' 'Preflight finished: no installation, Git mutation, service start, or network exposure.'
exit 0
