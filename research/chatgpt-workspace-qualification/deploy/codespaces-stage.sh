#!/usr/bin/env bash
# Codespaces qualification bootstrap: no public ports, no service activation.
# Run with "bash <path>"; NEVER source in an interactive terminal.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "ERROR: run this file with bash, not source" >&2
  return 2
fi
set -euo pipefail
umask 077

ROOT=/workspaces/Public
BRANCH=experiments/chatgpt-workspace-qualification
PIN=dec01b9f50f966097ddfc84d357d12a52f238935
UPSTREAM=https://github.com/fwerkor/local-shell-mcp.git
STAGE="$HOME/.local/share/public-chatgpt-mcp-stage"
SOURCE="$STAGE/local-shell-mcp"
VENV="$STAGE/venv"
abort() { echo "BLOCKED: $*" >&2; exit 2; }

[[ "$(id -un)" == codespace ]] || abort "run as the unprivileged codespace login; do not use sudo"
[[ -d "$ROOT" ]] || abort "expected workspace not present: $ROOT"
[[ "$(git -C "$ROOT" rev-parse --show-toplevel)" == "$ROOT" ]] || abort "workspace root mismatch"
remote="$(git -C "$ROOT" remote get-url origin)"
case "$remote" in
  https://github.com/Binilts03/Public|https://github.com/Binilts03/Public.git|git@github.com:Binilts03/Public.git) ;;
  *) abort "origin is not the allowlisted Public repository";;
esac
[[ "$(git -C "$ROOT" branch --show-current)" == "$BRANCH" ]] || abort "wrong branch"
[[ -z "$(git -C "$ROOT" status --porcelain)" ]] || abort "Public worktree is not clean; do not reset or overwrite it"
[[ ! -d /run/systemd/system ]] || abort "this is a Codespaces-only bootstrap; use VM qualification on systemd hosts"

echo "1/5 Installing uv in the Codespaces user environment if missing"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  if command -v pipx >/dev/null 2>&1; then
    pipx install uv
  elif python3 -m pipx --version >/dev/null 2>&1; then
    python3 -m pipx install uv
  else
    abort "pipx is missing; install uv using https://docs.astral.sh/uv/getting-started/installation/"
  fi
fi
command -v uv >/dev/null 2>&1 || abort "uv was installed but is not on PATH"
uv --version

echo "2/5 Installing Python 3.12 (separate from Codespaces Python 3.14)"
uv python install 3.12

echo "3/5 Fetching pinned public MCP backend (read-only upstream)"
mkdir -p "$STAGE"
chmod 0700 "$STAGE"
if [[ ! -d "$SOURCE/.git" ]]; then
  [[ ! -e "$SOURCE" ]] || abort "source directory exists but is not a Git clone"
  GIT_TERMINAL_PROMPT=0 git -c credential.helper= clone --filter=blob:none "$UPSTREAM" "$SOURCE"
fi
[[ "$(git -C "$SOURCE" remote get-url origin)" == "$UPSTREAM" ]] || abort "upstream remote mismatch"
[[ -z "$(git -C "$SOURCE" status --porcelain)" ]] || abort "upstream copy modified; no reset performed"
GIT_TERMINAL_PROMPT=0 git -C "$SOURCE" -c credential.helper= fetch origin "$PIN"
git -C "$SOURCE" checkout --detach "$PIN"
[[ "$(git -C "$SOURCE" rev-parse HEAD)" == "$PIN" ]] || abort "upstream SHA mismatch"

echo "4/5 Creating isolated Python 3.12 virtualenv for LOCAL qualification only"
if [[ -x "$VENV/bin/python" ]]; then
  "$VENV/bin/python" -c 'import sys; assert sys.version_info[:2] == (3, 12)' \
    || abort "existing venv is not Python 3.12; do not overwrite automatically"
else
  uv venv --python 3.12 "$VENV"
fi
uv pip install --python "$VENV/bin/python" "$SOURCE[dev]"
"$VENV/bin/python" -c 'import local_shell_mcp; print("MCP_BACKEND_IMPORT_PASS")'

echo "5/5 Running independent disposable-file MCP checks (no public listener)"
export REPORT_PATH="$STAGE/inprocess-report.json"
"$VENV/bin/python" "$ROOT/research/chatgpt-workspace-qualification/candidate_fwerkor.py"
"$VENV/bin/python" -c 'import json,os; x=json.load(open(os.environ["REPORT_PATH"])); assert x["summary"]["FAIL"] == 0; print("INPROCESS_GATE_PASS")'

echo
echo "STAGING_PASS: Python 3.12 pinned backend imported and independent checks passed."
echo "Backend SHA: $(git -C "$SOURCE" rev-parse HEAD)"
echo "Report: $REPORT_PATH"
echo "NO_PUBLIC_ENDPOINT: Controller, worker, OAuth, and port forwarding remain unconfigured."
echo "SECURITY: Staged code belongs to codespace user; it is NOT an isolated worker deployment."
