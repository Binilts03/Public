#!/usr/bin/env python3
"""Fail-closed static review of STAGED two-user package (does not run installer)."""
from pathlib import Path
import configparser
import re
import subprocess
import sys

root=Path(__file__).resolve().parent
installer=root/"install-staged.sh"
controller=root/"chatgpt-coder.service"
worker=root/"chatgpt-worker.service"
launcher=root/"nondumpable_mcp_entrypoint.py"
for file in (installer,controller,worker,launcher):
    assert file.is_file(),file

subprocess.run(["bash","-n",str(installer)],check=True)
subprocess.run([sys.executable,"-m","py_compile",str(launcher)],check=True)
def read_unit(path):
    config=configparser.ConfigParser(interpolation=None,strict=False)
    assert config.read(path)
    return config["Service"]
a=read_unit(controller)
b=read_unit(worker)
assert a["User"]=="chatgpt-controller"
assert a["Group"]=="chatgpt-controller"
assert b["User"]=="chatgpt-worker"
assert b["Group"]=="chatgpt-worker"
assert a["User"]!=b["User"]
assert a["EnvironmentFile"]=="/etc/chatgpt-coder/controller.env"
assert b["EnvironmentFile"]=="/etc/chatgpt-coder/worker.env"
assert "nondumpable_mcp_entrypoint.py" in a["ExecStart"]
assert "--remote" in a["ExecStart"]
assert "worker run" in b["ExecStart"]
assert a["ReadWritePaths"]=="/srv/chatgpt-controller"
assert b["ReadWritePaths"]=="/srv/chatgpt-worker"
for unit in (a,b):
    assert unit["NoNewPrivileges"]=="true"
    assert unit["ProtectHome"]=="true"
    assert unit["ProtectSystem"]=="strict"
    assert unit["KillMode"]=="control-group"
    assert unit["CapabilityBoundingSet"]==""
    assert unit["PrivateTmp"]=="true"

text=installer.read_text()
assert 'dirname -- "$0"' in text
assert "useradd --system --user-group" in text
assert 'if [[ "$(id -u "$CTRL")" == "$(id -u "$WORKER")" ]]' in text
assert "https://github.com/Binilts03/Public.git" in text
assert "https://github.com/fwerkor/local-shell-mcp.git" in text
assert "dec01b9f50f966097ddfc84d357d12a52f238935" in text
assert "remote set-url --push origin no-push://disabled" in text
assert "LOCAL_SHELL_MCP_DISABLE_LOCAL=true" in text
assert "LOCAL_SHELL_MCP_REMOTE_ENABLED=true" in text
assert "LOCAL_SHELL_MCP_AUTH_BYPASS_LOCALHOST=false" in text
assert "LOCAL_SHELL_MCP_OAUTH_JWT_SECRET=$JWT_SECRET" in text
assert 'grep -Eqi' in text
assert "REPLACE-WITH-AUTHORIZED-HOST.invalid" in text
assert "systemctl daemon-reload" in text
assert 'systemctl is-active --quiet "$unit"' in text
assert 'for unit in chatgpt-coder.service chatgpt-worker.service; do' in text
assert text.index('systemctl is-active --quiet "$unit"') < text.index('install -d -o "$CTRL"')
assert re.search(r'\bsystemctl\s+disable\b',text)
assert not re.search(r'(?m)^\s*(?:sudo\s+)?systemctl\s+(?:start|enable|restart)\b',text)
assert not re.search(r'(?im)^\s*(?:sudo\s+)?tailscale\s+funnel\b',text)
assert "LOCAL_SHELL_MCP_OAUTH_JWT_SECRET" not in b.get("Environment","")
print("PASS: staged two-UID controller/worker units; Public-only clone; disable_local; no pushes or service activation.")
print("NOTE: This is a STATIC contract only. OS sandbox, VM deployment, real private plugin and Codex parity still unverified.")
