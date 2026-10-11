#!/usr/bin/env python3
"""Probe live job recovery across a real local-shell-mcp OS process restart.

Only a disposable workspace and generated OAuth credentials. Distinguishes a
surviving job from a saved record, with no claim about systemd cgroup restarts.
"""
import asyncio
import json
import os
from pathlib import Path
import secrets
import tempfile
import time

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from real_process_oauth_e2e import port_available, server, oauth_login


async def run_mcp(url, token, action, job_id=None):
    async with httpx.AsyncClient(headers={"Authorization":"Bearer "+token},
                                  timeout=httpx.Timeout(15,read=50)) as http:
        async with streamable_http_client(url+"/mcp",http_client=http) as streams:
            async with ClientSession(streams[0],streams[1]) as session:
                await session.initialize()
                listed=await session.list_tools()
                toolset={x.name for x in listed.tools}
                assert {"job_start","job_list","job_tail","job_stop"} <= toolset
                if action=="start":
                    command=("python3 -c 'from pathlib import Path; import time; "
                             "time.sleep(6); Path(\"job-finished.txt\").write_text(\"DONE\"); "
                             "print(\"JOB_RESTART_CANARY\")'")
                    outcome=await session.call_tool("job_start",{
                        "command":command,"cwd":".","name":"public-restart-fixture",
                        "idempotency_key":"qualification-single-background-command-v1"})
                    assert not outcome.isError,(outcome.structuredContent or {})
                    data=outcome.structuredContent or {}
                    assert data.get("ok"),data
                    job=data["data"]["job_id"]
                    assert job
                    listed_jobs=await session.call_tool("job_list",{})
                    assert not listed_jobs.isError,listed_jobs
                    assert job in json.dumps(listed_jobs.structuredContent or {})
                    return job
                assert job_id
                end=time.monotonic()+18
                last=None
                while time.monotonic()<end:
                    observed=await session.call_tool("job_list",{})
                    assert not observed.isError,(observed.structuredContent or {})
                    data=observed.structuredContent or {}
                    jobs=data.get("data",{}).get("jobs",[])
                    match=next((j for j in jobs if j.get("job_id")==job_id),None)
                    assert match is not None, ("Durable job record missing",data)
                    last=match
                    if match.get("status") in {"completed","failed","lost","stopped","cancelled"}:
                        break
                    await asyncio.sleep(.3)
                assert last is not None
                tailed=await session.call_tool("job_tail",{"job_id":job_id,"lines":50})
                assert not tailed.isError,(tailed.structuredContent or {})
                details=tailed.structuredContent or {}
                return {"job":last,"tail":details.get("data",{})}


def main():
    with tempfile.TemporaryDirectory(prefix="public-job-restart-") as tmp:
        root=Path(tmp)
        work=root/"workspace";work.mkdir()
        port=port_available()
        url=f"http://127.0.0.1:{port}"
        secret=secrets.token_hex(40)
        pin=secrets.token_urlsafe(32)
        env={**os.environ,
             "LOCAL_SHELL_MCP_MODE":"mcp","LOCAL_SHELL_MCP_HOST":"127.0.0.1",
             "LOCAL_SHELL_MCP_PORT":str(port),
             "LOCAL_SHELL_MCP_WORKSPACE_ROOT":str(work),
             "LOCAL_SHELL_MCP_STATE_DIR":str(root/"state"),
             "LOCAL_SHELL_MCP_AUTH_MODE":"oauth",
             "LOCAL_SHELL_MCP_AUTH_BYPASS_LOCALHOST":"false",
             "LOCAL_SHELL_MCP_OAUTH_ADMIN_PIN":pin,
             "LOCAL_SHELL_MCP_OAUTH_JWT_SECRET":secret,
             "LOCAL_SHELL_MCP_OAUTH_ACCESS_TOKEN_TTL_S":"3600",
             "LOCAL_SHELL_MCP_PUBLIC_BASE_URL":url,
             "LOCAL_SHELL_MCP_REMOTE_ENABLED":"false",
             "LOCAL_SHELL_MCP_UI_ENABLED":"false",
             "LOCAL_SHELL_MCP_LIVE_WORKSPACE_ENABLED":"false",
             "LOCAL_SHELL_MCP_ALLOW_FULL_CONTAINER":"false"}
        log=root/"backend.log"
        started=time.monotonic()
        with server(env,url,log):
            token=oauth_login(url,pin,secret)
            jobid=asyncio.run(run_mcp(url,token,"start"))
        with server(env,url,log):
            verdict=asyncio.run(run_mcp(url,token,"inspect",jobid))
            assert verdict["job"]["job_id"]==jobid
            assert verdict["job"]["status"]=="completed",(verdict, "Expected successful completed job")
            assert verdict["job"]["exit_code"]==0,verdict
            assert (work/"job-finished.txt").read_text()=="DONE"
            assert "JOB_RESTART_CANARY" in json.dumps(verdict["tail"])
        report={"schema":"public-job-restart/v1","result":"PASS",
                "duration_s":round(time.monotonic()-started,2),
                "verified":["Background job started over authenticated MCP",
                            "OS MCP server process terminated mid-job, then restarted",
                            "Original job id remains discoverable and reconciles completed exit 0",
                            "Original job output and file artifact remain verifiable"],
                "warning":"This is process-only SIGTERM on disposable CI Ubuntu. Does not verify systemd cgroup termination, machine reboot or crash-atomic job status."}
        out=Path(os.environ.get("JOB_RESTART_REPORT","/tmp/public-job-restart.json"))
        out.write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2))


if __name__=="__main__":main()
