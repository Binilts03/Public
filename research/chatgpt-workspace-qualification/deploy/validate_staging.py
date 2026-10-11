#!/usr/bin/env python3
"""Static staging-package review. Does not install/start or expose anything."""
from pathlib import Path
import configparser
import subprocess
import sys

root=Path(__file__).resolve().parent
installer=root/"install-staged.sh"
service=root/"chatgpt-coder.service"
launcher=root/"nondumpable_mcp_entrypoint.py"
for file in (installer,service,launcher):
    assert file.is_file(),file
subprocess.run(["bash","-n",str(installer)],check=True)
subprocess.run([sys.executable,"-m","py_compile",str(launcher)],check=True)
unit=configparser.ConfigParser(interpolation=None,strict=False)
unit.read(service)
assert unit["Service"]["User"]=="chatgpt-coder"
assert "nondumpable_mcp_entrypoint.py" in unit["Service"]["ExecStart"]
assert unit["Service"]["NoNewPrivileges"]=="true"
assert unit["Service"]["ProtectHome"]=="true"
assert unit["Service"]["ProtectSystem"]=="strict"
assert unit["Service"]["KillMode"]=="control-group"
assert unit["Service"]["CapabilityBoundingSet"]==""
text=installer.read_text()
assert "https://github.com/Binilts03/Public.git" in text
assert 'no-push://disabled' in text
assert 'systemctl daemon-reload' in text
assert 'systemctl enable' not in text
assert 'systemctl start' not in text
assert 'tailscale funnel' not in text.lower()
assert "REPLACE-WITH-AUTHORIZED-HOST.invalid" in text
assert "dec01b9f50f966097ddfc84d357d12a52f238935" in text
print("PASS staged installer syntax, pinned upstream, Public-only clone, disabled push, nondumpable service.")
print("STAGED ONLY: no runtime deployment, no state-file isolation verified, no plugin connected.")
