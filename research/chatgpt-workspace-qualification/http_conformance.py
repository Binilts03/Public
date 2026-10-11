#!/usr/bin/env python3
"""Loopback-only HTTP/MCP and bearer authentication probe on a disposable fixture.
This is NOT production TLS/OAuth security verification.
"""
import argparse
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        return sock.getsockname()[1]

def send(port,body,token=None):
    con=http.client.HTTPConnection("127.0.0.1",port,timeout=5)
    headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream",
       "MCP-Protocol-Version":"2025-06-18"}
    if token is not None:
        headers["Authorization"]="Bearer "+token
    con.request("POST","/mcp",body=json.dumps(body).encode(),headers=headers)
    response=con.getresponse()
    data=response.read().decode(errors="replace")
    status=response.status
    con.close()
    if status==200:
        assert response.getheader("Content-Type","").lower().startswith("application/json"),data[:500]
        return status,json.loads(data)
    return status,data

def run(server):
    evidence=[]
    def gate(label,fn):
        try:
            detail=fn()
            evidence.append({"gate":label,"status":"PASS","detail":str(detail)[:300]})
        except Exception as e:
            evidence.append({"gate":label,"status":"FAIL","detail":str(e)[:500]})
    with tempfile.TemporaryDirectory(prefix="public-http-qual-") as d:
        path=Path(d)
        root=path/"fixture";root.mkdir()
        (root/"verify.txt").write_text("FIXTURE_CANARY\n")
        secret=secrets.token_urlsafe(36)
        config=path/"config.json"
        port=free_port()
        config.write_text(json.dumps({"workspaces":{"default":str(root)},
            "transport":{"type":"http","host":"127.0.0.1","port":port}}))
        env={**os.environ,"MCP_TOKEN":secret}
        process=subprocess.Popen(["node",str(server),"--config",str(config)],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=env)
        try:
            ready=False
            for _ in range(80):
                if process.poll() is not None: break
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.2):
                        ready=True; break
                except OSError: time.sleep(.1)
            if not ready:
                err=process.stderr.read().decode(errors="replace")[:500] if process.poll() is not None else "listen timeout"
                raise RuntimeError("Backend did not start: "+err)
            init={"jsonrpc":"2.0","id":1,"method":"initialize",
                  "params":{"protocolVersion":"2025-06-18","capabilities":{},
                            "clientInfo":{"name":"http-qualifier","version":"1"}}}
            def denied_none():
                status,_=send(port,init)
                assert status==401,status
                return "HTTP 401"
            gate("Reject missing bearer token",denied_none)
            def denied_wrong():
                status,_=send(port,init,"wrong-token")
                assert status==401,status
                return "HTTP 401"
            gate("Reject incorrect bearer token",denied_wrong)
            def initialize():
                status,payload=send(port,init,secret)
                assert status==200,(status,payload)
                assert payload.get("result",{}).get("serverInfo",{}).get("name")=="workspace-mcp",payload
                return payload["result"]["serverInfo"]["name"]
            gate("Authenticated HTTP initialize",initialize)
            def tools():
                status,payload=send(port,{"jsonrpc":"2.0","id":2,"method":"tools/list"},secret)
                assert status==200,(status,payload)
                names={x.get("name") for x in payload.get("result",{}).get("tools",[])}
                assert "read_file" in names and "workspace_list" in names,names
                assert "run_command" not in names and "start_job" not in names, "HTTP server unexpectedly exposes shell"
                return str(len(names))+" discovered; shell tools disabled"
            gate("HTTP tools/list and no default shell",tools)
            def read():
                status,payload=send(port,{"jsonrpc":"2.0","id":3,"method":"tools/call",
                    "params":{"name":"read_file","arguments":{"path":"verify.txt"}}},secret)
                assert status==200,(status,payload)
                result=payload.get("result",{})
                assert result.get("isError") is not True,result
                assert any("FIXTURE_CANARY" in x.get("text","") for x in result.get("content",[])),result
                return "Fixture canary read via authenticated HTTP"
            gate("Authenticated HTTP tool execution",read)
            def traversal():
                status,payload=send(port,{"jsonrpc":"2.0","id":4,"method":"tools/call",
                    "params":{"name":"read_file","arguments":{"path":"../forbidden"}}},secret)
                assert status==200,status
                assert payload.get("result",{}).get("isError") is True,payload
                return "Path traversal refused"
            gate("HTTP path traversal denied",traversal)
            gate("Fixture unchanged",lambda: root.joinpath("verify.txt").read_text()=="FIXTURE_CANARY\n" or (_ for _ in ()).throw(AssertionError("Fixture unexpectedly changed")))
        except Exception as e:
            evidence.append({"gate":"HTTP backend startup","status":"BLOCKED","detail":str(e)[:500]})
        finally:
            process.terminate()
            try: process.wait(timeout=4)
            except subprocess.TimeoutExpired: process.kill()
            process.stderr.close()
    stats={s:sum(x["status"]==s for x in evidence) for s in ["PASS","FAIL","BLOCKED"]}
    return {"schema":"workspace-http-qualification/v1","results":evidence,"summary":stats,
        "limit":"Only loopback HTTP and static bearer tested. No public TLS, OAuth, tunnel, ChatGPT plugin, sandbox, or Codex parity verified."}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--server-js",type=Path,required=True)
    ap.add_argument("--output",type=Path,default=Path("http-result.json"))
    args=ap.parse_args()
    report=run(args.server_js.resolve())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report["summary"]))
    for row in report["results"]:print(row["status"],row["gate"],row["detail"][:140])
    return 1 if report["summary"]["FAIL"] or report["summary"]["BLOCKED"] else 0
if __name__=="__main__": sys.exit(main())
