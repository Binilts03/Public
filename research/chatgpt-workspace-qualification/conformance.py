#!/usr/bin/env python3
"""Disposable black-box conformance probe for workspace-mcp (not Codex parity).
Runs only against a temporary Git fixture; never points at an existing repo.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time

PROTOCOL="2025-06-18"
REQUIRED={"workspace_list","read_file","patch","git_status","git_diff","run_command","start_job","job_status","harness_skill"}

class Client:
    def __init__(self, command):
        self.command=command
        self.next_id=0
        self.messages=queue.Queue()
        self.stderr=[]
    def __enter__(self):
        self.proc=subprocess.Popen(self.command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        def read_stdout():
            for raw in self.proc.stdout:
                try: self.messages.put(json.loads(raw))
                except Exception as e: self.messages.put({"_error":str(e),"raw":raw.decode(errors="replace")[:300]})
            self.messages.put({"_eof":True})
        def read_stderr():
            for raw in self.proc.stderr:
                self.stderr.append(raw.decode(errors="replace")[:500])
        threading.Thread(target=read_stdout,daemon=True).start()
        threading.Thread(target=read_stderr,daemon=True).start()
        return self
    def send(self,item):
        self.proc.stdin.write((json.dumps(item)+"\n").encode())
        self.proc.stdin.flush()
    def request(self,method,params=None,timeout=25):
        self.next_id+=1
        key=self.next_id
        self.send({"jsonrpc":"2.0","id":key,"method":method,"params":params or {}})
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            try: result=self.messages.get(timeout=max(.01,deadline-time.monotonic()))
            except queue.Empty: break
            if result.get("_eof") or result.get("_error"):
                raise RuntimeError("MCP stdout lost: "+str(result)+" stderr: "+"".join(self.stderr[-4:]))
            if result.get("id")==key:
                if "error" in result: raise RuntimeError(str(result["error"]))
                return result.get("result",{})
        raise TimeoutError(method+" timed out; stderr "+"".join(self.stderr[-4:]))
    def init(self):
        x=self.request("initialize",{"protocolVersion":PROTOCOL,"capabilities":{},"clientInfo":{"name":"public-qualification","version":"1"}})
        self.send({"jsonrpc":"2.0","method":"notifications/initialized"})
        return x
    def call(self,tool_name,**kwargs):
        return self.request("tools/call",{"name":tool_name,"arguments":kwargs})
    def __exit__(self,*_):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:self.proc.wait(timeout=4)
            except subprocess.TimeoutExpired:self.proc.kill()
        for pipe in [self.proc.stdin,self.proc.stdout,self.proc.stderr]:
            try:pipe.close()
            except Exception:pass

def text(response):
    return "\n".join(part.get("text","") for part in response.get("content",[]) if part.get("type")=="text")
def success(response,contains=None):
    if response.get("isError"): raise AssertionError(text(response))
    out=text(response)
    if contains is not None and contains not in out:
        raise AssertionError("Expected "+repr(contains)+" in "+out[:500])
    return out
def rejected(response):
    if response.get("isError") is not True:
        raise AssertionError("Unexpected success: "+text(response)[:300])
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def git(root,*args):
    subprocess.run(["git",*args],cwd=root,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)

def run(server):
    results=[]
    def gate(name,fn):
        start=time.monotonic()
        try:
            note=str(fn() or "")[:250]
            results.append({"gate":name,"status":"PASS","duration_ms":int((time.monotonic()-start)*1000),"evidence":note})
        except Exception as error:
            results.append({"gate":name,"status":"FAIL","duration_ms":int((time.monotonic()-start)*1000),"evidence":str(error)[:500]})
    with tempfile.TemporaryDirectory(prefix="public-workspace-mcp-") as tmpdir:
        tmp=Path(tmpdir)
        root=tmp/"fixture";root.mkdir()
        (root/"src").mkdir()
        (root/"src/example.js").write_text("export const value = 41;\n")
        (root/"README.md").write_text("original heading\n")
        (root/"calc.mjs").write_text("export function add(a, b) { return a + b + 1; }\n")
        (root/"calc.test.mjs").write_text("import { test } from 'node:test';\nimport { strict as assert } from 'node:assert';\nimport { add } from './calc.mjs';\ntest('adds correctly', () => assert.equal(add(2,3),5));\n")
        git(root,"init","-q","-b","fixture")
        git(root,"add",".")
        git(root,"-c","user.name=Test","-c","user.email=test@example.invalid","commit","-qm","baseline")
        secret=tmp/"not-in-root.txt";secret.write_text("DO_NOT_READ_OR_MODIFY")
        (root/"link.txt").symlink_to(secret)
        skills=tmp/"skills"/"probe-skill";skills.mkdir(parents=True)
        (skills/"SKILL.md").write_text("---\nname: probe-skill\ndescription: safe test\n---\nSKILL_VERIFIED\n")
        config=tmp/"config.json"
        config.write_text(json.dumps({"workspaces":{"default":str(root)},
            "shell":{"mode":"allowlist","allow":["node"]},
            "harness":{"session":True,"dbPath":str(tmp/"harness.sqlite"),"skillsDir":str(tmp/"skills")}}))
        try:
            with Client(["node",str(server),"--config",str(config)]) as client:
                init={}
                def initialize():
                    nonlocal init
                    init=client.init()
                    assert init.get("serverInfo",{}).get("name"),init
                    return init["serverInfo"]["name"]
                gate("MCP protocol initialization",initialize)
                instructions=init.get("instructions","")
                if "redirect such requests to Marco" in instructions or "natural triggers" in instructions:
                    results.append({"gate":"Upstream author instruction contamination","status":"WARN",
                      "evidence":"Upstream server instructions are not suitable for adoption without adjustment."})
                tools=set()
                def discover():
                    nonlocal tools
                    tools={item["name"] for item in client.request("tools/list").get("tools",[])}
                    assert REQUIRED<=tools,"Missing "+str(sorted(REQUIRED-tools))
                    return len(tools)
                gate("Required tool discovery",discover)
                gate("Workspace scoping",lambda:success(client.call("workspace_list"),str(root)))
                gate("Read source",lambda:success(client.call("read_file",path="src/example.js"),"value = 41"))
                gate("Reject parent traversal",lambda:rejected(client.call("read_file",path="../not-in-root.txt")))
                gate("Reject symlink escape",lambda:rejected(client.call("read_file",path="link.txt")))
                def patch():
                    success(client.call("patch",edits=[
                      {"path":"src/example.js","oldString":"41","newString":"42"},
                      {"path":"README.md","oldString":"original heading","newString":"modified heading"}]))
                    assert (root/"src/example.js").read_text()=="export const value = 42;\n"
                    assert (root/"README.md").read_text()=="modified heading\n"
                gate("Multi-file patch",patch)
                def patch_failure():
                    before=[digest(root/"src/example.js"),digest(root/"README.md")]
                    rejected(client.call("patch",edits=[
                      {"path":"src/example.js","oldString":"42","newString":"99"},
                      {"path":"README.md","oldString":"MISSING_TEXT","newString":"oops"}]))
                    after=[digest(root/"src/example.js"),digest(root/"README.md")]
                    assert before==after,"Invalid patch changed at least one file"
                gate("Invalid patch no-write",patch_failure)
                gate("Git diff",lambda:success(client.call("git_diff"),"value = 42"))
                gate("Git status",lambda:success(client.call("git_status"),"example.js"))
                gate("Shell executes Node",lambda:success(client.call("run_command",command=["node","--version"]),"exit code: 0"))
                def repair_red_green():
                    red=success(client.call("run_command",command=["node","--test","calc.test.mjs"]))
                    assert "exit code: 1" in red, "Expected actual RED test, got: "+red[:400]
                    success(client.call("patch",edits=[{"path":"calc.mjs","oldString":"a + b + 1","newString":"a + b"}]))
                    green=success(client.call("run_command",command=["node","--test","calc.test.mjs"]))
                    assert "exit code: 0" in green, "Test remained failing: "+green[:400]
                    assert "a + b;" in (root/"calc.mjs").read_text()
                    assert "return a + b + 1" in subprocess.run(["git","show","HEAD:calc.mjs"],cwd=root,check=True,capture_output=True,text=True).stdout
                    assert "calc.mjs" in success(client.call("git_diff"))
                    return "RED exit 1; patched via MCP; GREEN exit 0; baseline HEAD unchanged"
                gate("Real RED-GREEN repair through MCP",repair_red_green)
                def background():
                    result=success(client.call("start_job",command=["node","-e","setTimeout(()=>console.log('JOB_DONE'),250)"],name="fixture-background"))
                    match=re.search(r"jobId:\s*(\S+)",result)
                    assert match,"No job ID returned"
                    end=time.monotonic()+12
                    while time.monotonic()<end:
                        status=success(client.call("job_status",jobId=match.group(1)))
                        if "exited  exit code: 0" in status:
                            assert "JOB_DONE" in status,status
                            return match.group(1)
                        time.sleep(.2)
                    raise TimeoutError("Job did not complete")
                gate("Background process and log",background)
                def skill():
                    assert "harness_skill" in tools
                    success(client.call("harness_skill",action="list"),"probe-skill")
                    success(client.call("harness_skill",action="get",name="probe-skill"),"SKILL_VERIFIED")
                gate("Skill discovery and read",skill)
                gate("Unrelated file unchanged",lambda:secret.read_text()=="DO_NOT_READ_OR_MODIFY" or (_ for _ in ()).throw(AssertionError("outside file changed")))
        except Exception as error:
            results.append({"gate":"Backend startup/session","status":"BLOCKED","evidence":str(error)[:500]})
    summary={status:sum(x["status"]==status for x in results) for status in ("PASS","FAIL","WARN","BLOCKED")}
    return {"schema":"workspace-qualification/v1","upstream_js":str(server),"summary":summary,"results":results,
        "limit":"Tests only disposable filesystem operations. Does not prove OAuth, sandboxing, job-restart recovery, ChatGPT tool invocation or Codex task parity."}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--server-js",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=Path("qualification.json"))
    args=parser.parse_args()
    report=run(args.server_js.resolve())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report["summary"]))
    for r in report["results"]:
        print(r["status"],r["gate"],r.get("evidence","")[:130])
    return 1 if report["summary"]["FAIL"] or report["summary"]["BLOCKED"] else 0
if __name__=="__main__":sys.exit(main())
