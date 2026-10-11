#!/usr/bin/env python3
"""Security gate: can an MCP shell tool read its OAuth server's process secret?

This deliberately probes /proc with a random TEST secret only. Never print
tokens or secrets. A detected leak must cause a non-zero CI result.
"""
import asyncio
import json
import os
from pathlib import Path
import secrets
import tempfile
import sys

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from real_process_oauth_e2e import port_available, server, oauth_login

async def probe(url,token):
    cmd=(
      "python3 -c 'import os,pathlib;"
      " own=os.getpid();"
      " seen=False;"
      " needle=b\"LOCAL_SHELL_MCP_OAUTH_JWT_SECRET=\";"
      " ps=[x for x in pathlib.Path(\"/proc\").iterdir() if x.name.isdigit()];"
      " blocks=[];"
      " exec(\"for p in ps:\\n"
      "  try:\\n"
      "   raw=(p/\\\"environ\\\").read_bytes()\\n"
      "   if needle in raw: blocks.append(p.name)\\n"
      "  except (OSError,PermissionError): pass\");"
      " print(\"SERVER_SECRET_VISIBLE=\"+str(bool(blocks)).lower())'"
    )
    async with httpx.AsyncClient(headers={"Authorization":"Bearer "+token},
                                  timeout=httpx.Timeout(15,read=50)) as http:
      async with streamable_http_client(url+"/mcp",http_client=http) as streams:
        async with ClientSession(streams[0],streams[1]) as session:
          await session.initialize()
          result=await session.call_tool("run_shell",{"command":cmd,"cwd":".","timeout_s":12})
          if result.isError:
            raise RuntimeError("MCP refused probe; boundary inconclusive: "+str(result.structuredContent)[:300])
          payload=result.structuredContent or {}
          assert payload.get("ok"),payload
          data=payload["data"]
          output=json.dumps(data)
          assert data.get("exit_code")==0,{"exit_code":data.get("exit_code"),"output":output[:450]}
          if "SERVER_SECRET_VISIBLE=true" in output:
            return {"verdict":"FAIL","reason":"shell user can read MCP OAuth process environment via /proc"}
          if "SERVER_SECRET_VISIBLE=false" in output:
            return {"verdict":"PASS","reason":"test cannot read MCP OAuth process env (not comprehensive isolation)"}
          return {"verdict":"INCONCLUSIVE","reason":"probe output not recognized"}

def main():
  with tempfile.TemporaryDirectory(prefix="public-credential-test-") as tmp:
    root=Path(tmp)
    workspace=root/"workspace"; workspace.mkdir()
    port=port_available()
    url=f"http://127.0.0.1:{port}"
    secret=secrets.token_hex(40)
    pin=secrets.token_urlsafe(32)
    env={**os.environ,
      "LOCAL_SHELL_MCP_MODE":"mcp",
      "LOCAL_SHELL_MCP_HOST":"127.0.0.1",
      "LOCAL_SHELL_MCP_PORT":str(port),
      "LOCAL_SHELL_MCP_WORKSPACE_ROOT":str(workspace),
      "LOCAL_SHELL_MCP_STATE_DIR":str(root/"state"),
      "LOCAL_SHELL_MCP_AUTH_MODE":"oauth",
      "LOCAL_SHELL_MCP_AUTH_BYPASS_LOCALHOST":"false",
      "LOCAL_SHELL_MCP_OAUTH_ADMIN_PIN":pin,
      "LOCAL_SHELL_MCP_OAUTH_JWT_SECRET":secret,
      "LOCAL_SHELL_MCP_OAUTH_ACCESS_TOKEN_TTL_S":"3600",
      "LOCAL_SHELL_MCP_PUBLIC_BASE_URL":url,
      "LOCAL_SHELL_MCP_REMOTE_ENABLED":"false",
      "LOCAL_SHELL_MCP_UI_ENABLED":"false",
      "LOCAL_SHELL_MCP_ALLOW_FULL_CONTAINER":"false",
      "PUBLIC_MCP_LAUNCHER":str(Path(__file__).resolve().parent/"nondumpable_mcp_entrypoint.py")}
    with server(env,url,root/"backend.log"):
      token=oauth_login(url,pin,secret)
      result=asyncio.run(probe(url,token))
    report={"schema":"credential-boundary/v1","test":"proc environ read by authenticated MCP run_shell",
            **result,"limit":"Only evaluates same-UID /proc access on hosted Ubuntu; no TLS or sandbox was applied."}
    target=Path(os.environ.get("SECURITY_REPORT","/tmp/public-credential-boundary.json"))
    target.write_text(json.dumps(report,indent=2)+"\n")
    print("Security verdict:",result["verdict"],result["reason"])
    if result["verdict"]!="PASS":
      print("BLOCKER: Do not expose a shell-enabled OAuth server in this configuration.")
      return 1
    return 0

if __name__=="__main__":
  sys.exit(main())
