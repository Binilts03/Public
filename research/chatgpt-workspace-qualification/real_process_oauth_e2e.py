#!/usr/bin/env python3
"""Actual loopback OAuth/PKCE -> Streamable HTTP MCP -> OS process restart probe.

Only temp fixtures. Never installs or touches a user repository or public endpoint.
All HTTPS/TLS, external ChatGPT authorization and OS sandboxing remain UNTESTED.
"""
import asyncio
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def port_available():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def challenge(verifier):
    raw = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@contextmanager
def server(env, url, logs):
    with open(logs, "a", encoding="utf-8") as handle:
        executable = ([sys.executable, env["PUBLIC_MCP_LAUNCHER"]] if env.get("PUBLIC_MCP_LAUNCHER")
                      else ["local-shell-mcp"])
        process = subprocess.Popen(
            [*executable, "--mode", "mcp", *([] if env.get("PUBLIC_MCP_ALLOW_REMOTE_TEST")=="1" else ["--no-remote"])],
            env=env, stdin=subprocess.DEVNULL,
            stdout=handle, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("MCP server exited before ready; inspect private test logs")
                try:
                    with httpx.Client(timeout=1) as client:
                        response = client.get(url + "/healthz")
                    if response.status_code == 200:
                        break
                except (httpx.HTTPError, OSError):
                    pass
                time.sleep(.15)
            else:
                raise TimeoutError("MCP backend never became ready on loopback")
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=4)


def oauth_login(url, admin_pin, jwt_secret):
    redirect="https://client.example.invalid/callback"
    verifier=secrets.token_urlsafe(64)
    state=secrets.token_urlsafe(20)
    with httpx.Client(base_url=url, follow_redirects=False, timeout=8) as c:
        meta=c.get("/.well-known/oauth-authorization-server")
        assert meta.status_code==200, (meta.status_code,meta.text[:300])
        assert "S256" in meta.json()["code_challenge_methods_supported"]
        reg=c.post("/oauth/register", json={
            "client_name":"public-qualification-ci",
            "redirect_uris":[redirect],
        })
        assert reg.status_code in (200,201), (reg.status_code,reg.text[:400])
        client_id=reg.json()["client_id"]
        params={
            "response_type":"code",
            "client_id":client_id,
            "redirect_uri":redirect,
            "code_challenge":challenge(verifier),
            "code_challenge_method":"S256",
            "state":state,
            "resource":url,
        }
        consent=c.get("/oauth/authorize", params=params)
        assert consent.status_code==200, (consent.status_code,consent.text[:350])
        approved=c.post("/oauth/authorize", data={**params, "pin":admin_pin})
        assert approved.status_code==302, (approved.status_code,approved.text[:350])
        query=parse_qs(urlsplit(approved.headers["location"]).query)
        assert query.get("state")==[state], "OAuth state lost"
        code=query["code"][0]
        wrong=c.post("/oauth/token", data={
            "grant_type":"authorization_code",
            "client_id":client_id,
            "code":code,
            "redirect_uri":redirect,
            "code_verifier":"wrong-but-otherwise-well-formed",
        })
        assert wrong.status_code==400, ("Wrong PKCE unexpectedly accepted",wrong.status_code)
        token_resp=c.post("/oauth/token", data={
            "grant_type":"authorization_code",
            "client_id":client_id,
            "code":code,
            "redirect_uri":redirect,
            "code_verifier":verifier,
        })
        assert token_resp.status_code==200,(token_resp.status_code,token_resp.text[:300])
        payload=token_resp.json()
        assert payload.get("token_type","").lower()=="bearer"
        assert payload.get("expires_in")==3600, "Expected nonpermanent access token"
        reuse=c.post("/oauth/token", data={
            "grant_type":"authorization_code",
            "client_id":client_id,
            "code":code,
            "redirect_uri":redirect,
            "code_verifier":verifier,
        })
        assert reuse.status_code==400, ("OAuth authorization code reused",reuse.status_code)
        claims=jwt.decode(payload["access_token"], jwt_secret, algorithms=["HS256"],
                          audience=url, issuer=url)
        assert claims["client_id"]==client_id
        assert "exp" in claims and claims["exp"]>claims["iat"]
        return payload["access_token"]


async def tool_session(url, token, operation, session_id=None):
    headers={"Authorization":"Bearer "+token}
    async with httpx.AsyncClient(headers=headers,timeout=httpx.Timeout(20,read=90)) as http:
        async with streamable_http_client(url+"/mcp",http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as client:
                init=await client.initialize()
                assert init.serverInfo.name
                listed=await client.list_tools()
                names={x.name for x in listed.tools}
                assert {"session_manage","skill_list","skill_load","file_read"}<=names
                if operation=="start":
                    skill_list=await client.call_tool("skill_list",{})
                    assert skill_list.isError is not True,skill_list
                    skill_text=json.dumps(skill_list.structuredContent or {},sort_keys=True)
                    assert "qualification-skill" in skill_text,skill_text[:600]
                    loaded=await client.call_tool("skill_load",{"name":"qualification-skill"})
                    assert loaded.isError is not True,loaded
                    assert "PINNED_SKILL_CANARY" in json.dumps(loaded.structuredContent or {})
                    started=await client.call_tool("session_manage",{
                        "action":"start","label":"Public test only",
                        "objective":"Verify durable task state across a real MCP server restart"})
                    assert not started.isError,started
                    payload=started.structuredContent
                    assert payload and payload.get("ok"),payload
                    sid=payload["data"]["session_id"]
                    report=await client.call_tool("session_manage",{
                        "action":"report","session_id":sid,
                        "summary":"Restart verification checkpoint saved",
                        "next":"Stop server then resume from a separate OS process"})
                    assert not report.isError,(report.structuredContent or {})
                    return sid
                assert session_id
                recovered=await client.call_tool("session_manage",{
                    "action":"resume","session_id":session_id})
                assert not recovered.isError,recovered
                payload=recovered.structuredContent or {}
                assert payload.get("ok"),payload
                assert "Restart verification checkpoint saved" in json.dumps(payload),payload
                return session_id


def main():
    with tempfile.TemporaryDirectory(prefix="public-auth-process-") as dirname:
        root=Path(dirname)
        fixture=root/"workspace"
        fixture.mkdir()
        skills=fixture/".agents"/"skills"/"qualification-skill"
        skills.mkdir(parents=True)
        (skills/"SKILL.md").write_text(
            "---\nname: qualification-skill\ndescription: Probe remote skill fidelity\n---\n"
            "PINNED_SKILL_CANARY\n",encoding="utf-8")
        outside=root/"outside-repo.txt"
        outside.write_text("UNTOUCHED\n")
        port=port_available()
        url=f"http://127.0.0.1:{port}"
        jwt_secret=secrets.token_hex(40)
        admin_pin=secrets.token_urlsafe(35)
        env={**os.environ,
            "LOCAL_SHELL_MCP_MODE":"mcp",
            "LOCAL_SHELL_MCP_HOST":"127.0.0.1",
            "LOCAL_SHELL_MCP_PORT":str(port),
            "LOCAL_SHELL_MCP_WORKSPACE_ROOT":str(fixture),
            "LOCAL_SHELL_MCP_STATE_DIR":str(root/"state"),
            "LOCAL_SHELL_MCP_AUTH_MODE":"oauth",
            "LOCAL_SHELL_MCP_AUTH_BYPASS_LOCALHOST":"false",
            "LOCAL_SHELL_MCP_OAUTH_ADMIN_PIN":admin_pin,
            "LOCAL_SHELL_MCP_OAUTH_JWT_SECRET":jwt_secret,
            "LOCAL_SHELL_MCP_OAUTH_ACCESS_TOKEN_TTL_S":"3600",
            "LOCAL_SHELL_MCP_PUBLIC_BASE_URL":url,
            "LOCAL_SHELL_MCP_REMOTE_ENABLED":"false",
            "LOCAL_SHELL_MCP_UI_ENABLED":"false",
            "LOCAL_SHELL_MCP_LIVE_WORKSPACE_ENABLED":"false",
            "LOCAL_SHELL_MCP_ALLOW_FULL_CONTAINER":"false"}
        logpath=root/"private-server.log"
        with server(env,url,logpath):
            with httpx.Client(timeout=5) as c:
                init_payload={"jsonrpc":"2.0","id":1,"method":"initialize",
                    "params":{"protocolVersion":"2025-06-18","capabilities":{},
                              "clientInfo":{"name":"security-negative","version":"1"}}}
                headers={"Accept":"application/json, text/event-stream",
                    "Content-Type":"application/json"}
                assert c.post(url+"/mcp",json=init_payload,headers=headers).status_code==401
                assert c.post(url+"/mcp",json=init_payload,
                    headers={**headers,"Authorization":"Bearer invalid"}).status_code==401
            token=oauth_login(url,admin_pin,jwt_secret)
            sid=asyncio.run(tool_session(url,token,"start"))
        assert outside.read_text()=="UNTOUCHED\n"
        with server(env,url,logpath):
            recovered=asyncio.run(tool_session(url,token,"resume",sid))
            assert recovered==sid
        report={
            "schema":"public-loopback-e2e/v1",
            "verified":[
                "MCP started in a separate Linux OS process bound only to loopback",
                "OAuth discovery/registration/consent authorization-code S256 PKCE",
                "Rejected wrong PKCE, invalid/missing bearer and OAuth code reuse",
                "Issued expiring 3600-second OAuth token, authenticated MCP SDK session",
                "Skill discover and exact instruction content over Streamable HTTP",
                "Created/reported a durable logical task over remote MCP",
                "Terminated server, restarted new OS process, resumed exact logical task",
                "Unrelated file unchanged",
            ],
            "not_verified":"Production TLS, third-party ChatGPT plugin, secure tunnel, OS sandbox, true job-process survival, Codex output parity",
            "result":"PASS"
        }
        output=Path(os.environ.get("E2E_REPORT","/tmp/public-real-process-e2e.json"))
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2))
        return 0


if __name__=="__main__":
    sys.exit(main())
