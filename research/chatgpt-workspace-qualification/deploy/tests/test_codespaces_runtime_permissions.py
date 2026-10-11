#!/usr/bin/env python3
"""Disposable regression: simulate a root-created umask=077 venv and repair.

No services, production paths, Git remotes, or credentials accessed.
Run in disposable CI: sudo python3 test_codespaces_runtime_permissions.py
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile

SCRIPT = Path(__file__).resolve().parents[1] / "codespaces-repair-runtime.py"


def load():
    spec = importlib.util.spec_from_file_location("codespaces_repair_runtime", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    assert os.geteuid() == 0, "Run only on a disposable CI root"
    module = load()
    with tempfile.TemporaryDirectory(prefix="public-mcp-venv-perm-test-") as dirname:
        root = Path(dirname)
        os.chmod(root, 0o755)
        venv = root / "venv"
        package = venv / "lib" / "python3.12" / "site-packages" / "public_fixture"
        saved_umask = os.umask(0o077)
        try:
            package.mkdir(parents=True)
            (package / "fixture.py").write_text("FIXTURE_ONLY = 1\n")
        finally:
            os.umask(saved_umask)
        assert stat.S_IMODE(venv.stat().st_mode) == 0o700
        assert stat.S_IMODE((package / "fixture.py").stat().st_mode) == 0o600
        count = module.repair_public_code_venv(venv)
        assert count >= 5
        assert stat.S_IMODE(venv.stat().st_mode) == 0o755
        assert stat.S_IMODE((package / "fixture.py").stat().st_mode) == 0o644
        count2 = module.repair_public_code_venv(venv)
        assert count2 == count, "repeat must be idempotent"
        print("PASS: root-owned venv umask 077 → 755 directories and 644 code; idempotent")

        external = root / "external-private"
        external.mkdir(mode=0o700)
        (package / "escape").symlink_to(external)
        before = stat.S_IMODE((package / "fixture.py").stat().st_mode)
        try:
            module.repair_public_code_venv(venv)
        except module.Blocked:
            pass
        else:
            raise AssertionError("symlink outside allowlist was accepted")
        assert stat.S_IMODE((package / "fixture.py").stat().st_mode) == before
        print("PASS: unsafe symlink aborts before any venv chmod")

    print("PASS: no services or persistent paths modified")


if __name__ == "__main__":
    main()
