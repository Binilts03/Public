#!/usr/bin/env python3
"""Defense-in-depth: launch pinned local-shell-mcp with nondumpable server process.

Requires Linux. This prevents same-UID shell subprocesses from inspecting
the server's /proc/<pid>/environ. It does NOT isolate filesystem state,
network, or arbitrary tools. DO NOT treat it as a complete production sandbox.
"""
import ctypes
import os
import sys

PR_SET_DUMPABLE = 4

def main():
    if sys.platform != "linux":
        raise SystemExit("This host hardening launcher is Linux-only")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))
    from local_shell_mcp.main import main as lsm_main
    lsm_main()

if __name__=="__main__":
    main()
