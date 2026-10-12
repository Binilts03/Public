"""Static fail-closed one-time Codespace staging contract.

Real named-UID ACL behavior is already exercised in Public's isolated
Ubuntu workflow. Never run the stage script in these tests.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STAGE = ROOT / "codespaces-stage-gateway.sh"
GATEWAY = ROOT / "gateway.py"


def test_stage_is_explicitly_opt_in_and_public_repo_only():
    source = STAGE.read_text()
    assert '[[ "$#" == 1 && "$1" == "--stage-only" ]]' in source
    assert '[[ "$EUID" == 0' in source
    assert 'SUDO_USER:-' in source
    assert "experiments/chatgpt-workspace-qualification" in source
    assert "/workspaces/Public" in source
    assert "https://github.com/Binilts03/Public" in source
    assert 'status --porcelain' in source
    assert "root:600" in source
    assert 'codespaces-isolation-qualified' in source
    assert '[[ ! -e "$STAGE"' in source
    assert 'gateway UID already exists' in source


def test_stage_changes_only_gateway_uid_parent_acl_and_root_owned_code():
    source = STAGE.read_text()
    assert "useradd --system --user-group" in source
    assert '--shell /usr/sbin/nologin "$GATE"' in source
    assert 'getfacl -p "$PARENT" > "$STATE/workspaces-parent-acl.before"' in source
    assert 'setfacl -n -m "u:$GATE:---" "$PARENT"' in source
    assert '"$SOURCE" "$STAGE/gateway.py"' in source
    assert 'sha256sum "$SOURCE"' in source
    assert 'sha256sum "$STAGE/gateway.py"' in source
    for expected in [
        'test ! -x "$PARENT"', 'test ! -r /srv/chatgpt-controller/controller.env',
        'test ! -x /srv/chatgpt-worker/worktrees/Public',
        'test ! -w "$sock"', 'test -w "$ORIGINAL"',
    ]:
        assert expected in source
    for forbidden in [
        'chmod -R', 'chown -R', 'setfacl -R', 'git push', 'git reset',
        'git checkout', 'git clean', 'remote_manage', 'worker enroll',
        'systemctl start', 'systemctl enable', 'cloudflared tunnel run',
        'gh codespace ports', 'docker run', 'curl ', 'wget ',
        'LOCAL_SHELL_MCP_AUTH_MODE=none', 'LOCAL_SHELL_MCP_OAUTH_JWT_SECRET=',
        'LOCAL_SHELL_MCP_OAUTH_ADMIN_PIN=',
    ]:
        assert forbidden not in source


def test_staged_gateway_will_require_separate_unprivileged_identity():
    source = GATEWAY.read_text()
    assert 'user.pw_name == "chatgpt-oauth-gateway"' in source
    assert 'os.geteuid() != 0' in source
    assert 'user.pw_shell == "/usr/sbin/nologin"' in source
    assert 'os.access("/workspaces", os.X_OK)' in source
    assert 'os.access("/srv/chatgpt-controller/controller.env", os.R_OK)' in source
    assert 'os.access("/srv/chatgpt-worker/worktrees/Public", os.X_OK)' in source
    assert 'require_dedicated_gateway_identity()' in source
