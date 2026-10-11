#!/usr/bin/env python3
"""Two-UID controller/worker security and real coding MCP smoke test.

Disposable GitHub-hosted Ubuntu ONLY. Uses sudo to create a CI user and test
paths; no project repository, secret, deployment host or Git remote is modified.
The worker receives only a one-time invite and has no controller OAuth secrets.
"""
import asyncio
import json
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys
import tempfile
import time

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from real_process_oauth_e2e import port_available, server, oauth_login

WORKER_USER="public-mcp-worker-ci"
WORKER_NAME="public-worker"

async def tools(url,token,mode,code=None,controller_state=None):
    async with httpx.AsyncClient(
        headers={"Authorization":"Bearer "+token},
        timeout=httpx.Timeout(15,read=80),
    ) as http:
        async with streamable_http_client(url+"/mcp",http_client=http) as streams:
            async with ClientSession(streams[0],streams[1]) as session:
                await session.initialize()
                registry={x.name for x in (await session.list_tools()).tools}
                assert {"remote_manage","run_shell","file_read"} <= registry,registry

                async def call(name,args):
                    result=await session.call_tool(name,args)
                    payload=result.structuredContent or {}
                    return result,payload

                if mode=="invite":
                    local,p=await call("run_shell",{"command":"echo NO_LOCAL_EXECUTION"})
                    assert local.isError or not p.get("ok"),("controller executed locally",p)
                    result,p=await call("remote_manage",{"action":"invite",
                        "name":WORKER_NAME,"workdir":code,"ttl_s":120})
                    assert not result.isError and p.get("ok"),p
                    invite=p["data"]["code"]
                    assert invite.startswith("lsmcp_inv_")
                    return invite

                if mode=="verify":
                    deadline=time.monotonic()+30
                    online=False
                    while time.monotonic()<deadline:
                        result,p=await call("remote_manage",{"action":"list"})
                        assert not result.isError and p.get("ok"),p
                        rows=p["data"]["machines"]
                        online=any(row["name"]==WORKER_NAME and row["status"]=="online" for row in rows)
                        if online: break
                        await asyncio.sleep(.4)
                    assert online,"Worker not enrolled/online after 30s"
                    command="python3 -c 'print(\"PUBLIC_WORKER_EXECUTION_PASS\")'"
                    result,p=await call("run_shell",{
                        "command":command,"machine":WORKER_NAME,"cwd":".","timeout_s":20})
                    assert not result.isError and p.get("ok"),p
                    assert p["data"]["exit_code"]==0,p
                    assert "PUBLIC_WORKER_EXECUTION_PASS" in json.dumps(p)

                    inspect=(
                        "from pathlib import Path;"
                        "import os;"
                        "secret=False;"
                        "needle=b\"LOCAL_SHELL_MCP_OAUTH_JWT_SECRET=\";"
                        "paths=[p for p in Path(\"/proc\").iterdir() if p.name.isdigit()];"
                        "exec(\"for p in paths:\\n"
                        " try:\\n"
                        "  b=(p/\\\"environ\\\").read_bytes()\\n"
                        "  if needle in b: secret=True\\n"
                        " except OSError: pass\");"
                        "state=Path("+repr(str(controller_state))+");"
                        "registry=state / \"oauth-clients.json\";"
                        "accessible=False;"
                        "exec(\"try:\\n"
                        " registry.read_bytes()\\n"
                        " accessible=True\\n"
                        "except OSError: pass\");"
                        "print(\"CTRL_SECRET_VISIBLE=\"+str(secret).lower());"
                        "print(\"CTRL_STATE_READABLE=\"+str(accessible).lower())"
                    )
                    result,p=await call("run_shell",{
                        "command":"python3 -c "+shlex.quote(inspect),
                        "machine":WORKER_NAME,"cwd":".","timeout_s":20})
                    assert not result.isError and p.get("ok"),p
                    assert p["data"]["exit_code"]==0,p
                    serialized=json.dumps(p)
                    assert "CTRL_SECRET_VISIBLE=false" in serialized,serialized[:750]
                    assert "CTRL_STATE_READABLE=false" in serialized,serialized[:750]
                    return {"remote_execution":"PASS","local_execution_denied":True,
                            "controller_environment_hidden":True,"controller_state_hidden":True}


def main():
    subprocess.run(["sudo","useradd","--system","--no-create-home",WORKER_USER],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    with tempfile.TemporaryDirectory(prefix="public-controller-boundary-") as d:
        root=Path(d)
        state=root/"auth-state"
        controller_workspace=root/"controller-workspace";controller_workspace.mkdir()
        worker_root=Path(tempfile.mkdtemp(prefix="public-worker-boundary-"))
        subprocess.run(["sudo","chown",WORKER_USER+":"+WORKER_USER,str(worker_root)],check=True)
        subprocess.run(["sudo","install","-d","-m","0700",
                        "-o",WORKER_USER,"-g",WORKER_USER,str(worker_root/"Public")],
                       check=True)
        worker_workspace=worker_root/"Public"
        port=port_available()
        url=f"http://127.0.0.1:{port}"
        secret=secrets.token_hex(42)
        pin=secrets.token_urlsafe(40)
        env={**os.environ,
            "LOCAL_SHELL_MCP_MODE":"mcp","LOCAL_SHELL_MCP_HOST":"127.0.0.1",
            "LOCAL_SHELL_MCP_PORT":str(port),
            "LOCAL_SHELL_MCP_WORKSPACE_ROOT":str(controller_workspace),
            "LOCAL_SHELL_MCP_STATE_DIR":str(state),
            "LOCAL_SHELL_MCP_DISABLE_LOCAL":"true",
            "LOCAL_SHELL_MCP_AUTH_MODE":"oauth",
            "LOCAL_SHELL_MCP_AUTH_BYPASS_LOCALHOST":"false",
            "LOCAL_SHELL_MCP_OAUTH_ADMIN_PIN":pin,
            "LOCAL_SHELL_MCP_OAUTH_JWT_SECRET":secret,
            "LOCAL_SHELL_MCP_OAUTH_ACCESS_TOKEN_TTL_S":"3600",
            "LOCAL_SHELL_MCP_PUBLIC_BASE_URL":url,
            "LOCAL_SHELL_MCP_REMOTE_ENABLED":"true",
            "LOCAL_SHELL_MCP_REMOTE_POLL_TIMEOUT_S":"1",
            "LOCAL_SHELL_MCP_REMOTE_PEER_TRANSFER_ENABLED":"false",
            "LOCAL_SHELL_MCP_UI_ENABLED":"false",
            "LOCAL_SHELL_MCP_ALLOW_FULL_CONTAINER":"false"}
        worker=None
        log=root/"controller.log"
        with server(env,url,log):
            token=oauth_login(url,pin,secret)
            invite=asyncio.run(tools(url,token,"invite",code=str(worker_workspace)))
            safe_env={k:v for k,v in os.environ.items()
                      if not k.startswith("LOCAL_SHELL_MCP_")}
            safe_env.update({
                "HOME":str(worker_root),
                "XDG_CONFIG_HOME":str(worker_root/".config"),
                "LOCAL_SHELL_MCP_WORKSPACE_ROOT":str(worker_workspace),
                "LOCAL_SHELL_MCP_WORKER_STATE_DIR":str(worker_root/"worker-identity"),
                "LOCAL_SHELL_MCP_STATE_DIR":str(worker_root/"state"),
                "LOCAL_SHELL_MCP_REMOTE_POLL_TIMEOUT_S":"1",
                "LOCAL_SHELL_MCP_REMOTE_ENABLED":"false",
                "LOCAL_SHELL_MCP_AUTH_MODE":"none",
                "LOCAL_SHELL_MCP_ALLOW_FULL_CONTAINER":"false",
            })
            command=["sudo","-u",WORKER_USER,"--",sys.executable,"-m",
                     "local_shell_mcp.remote_worker","connect",
                     "--server",url,"--invite",invite,
                     "--name",WORKER_NAME,"--workdir",str(worker_workspace)]
            with open(root/"worker.log","wb") as log_out:
                worker=subprocess.Popen(command,env=safe_env,
                    stdout=log_out,stderr=subprocess.STDOUT)
                try:
                    verdict=asyncio.run(tools(url,token,"verify",controller_state=state))
                    assert worker.poll() is None,"Worker died before verification"
                finally:
                    worker.terminate()
                    try:worker.wait(timeout=6)
                    except subprocess.TimeoutExpired:worker.kill();worker.wait(timeout=3)
        report={"schema":"public-dual-uid-boundary/v1","result":"PASS","verdict":verdict,
                "tested":"Distinct Linux UIDs, OAuth controller disable_local, enrolled worker, remote shell, controller environment/state unreadable",
                "limits":"CI only, not host systemd/reboot, not independent egress policy, not ChatGPT plugin, not full multi-tool attack surface or skill parity"}
        path=Path(os.environ.get("DUAL_UID_REPORT","/tmp/public-dual-uid.json"))
        path.write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
