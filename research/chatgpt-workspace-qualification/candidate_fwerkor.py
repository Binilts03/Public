#!/usr/bin/env python3
"""Independent in-process tool conformance for local-shell-mcp.
All operations use a temporary filesystem fixture. No network, public ingress, or real repos.
The upstream regression suite is run separately; this checks a user-visible tool loop.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import tempfile
import sys


def assert_good(result, name):
    assert isinstance(result, dict), (name, result)
    assert result.get("ok") is True, (name, result)
    return result.get("data") or {}


async def scenario(root: Path):
    os.environ["HOME"] = str(root / "home")
    os.environ["XDG_CONFIG_HOME"] = str(root / "home" / ".config")
    os.environ["LOCAL_SHELL_MCP_WORKSPACE_ROOT"] = str(root / "repo")
    os.environ["LOCAL_SHELL_MCP_STATE_DIR"] = str(root / ".state")
    os.environ["LOCAL_SHELL_MCP_AUTH_MODE"] = "none"   # Never use this for public deployment!
    os.environ["LOCAL_SHELL_MCP_REMOTE_ENABLED"] = "false"
    os.environ["LOCAL_SHELL_MCP_ALLOW_FULL_CONTAINER"] = "false"
    from local_shell_mcp.settings import get_settings
    from local_shell_mcp.tools import build_mcp

    get_settings.cache_clear()
    repo = root / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b + 1\n")
    (repo / "calc_test.py").write_text("from calc import add\nassert add(2, 3) == 5\n")
    skill_root = repo / ".agents" / "skills" / "independent-debug"
    skill_root.mkdir(parents=True)
    skill_body = "---\nname: independent-debug\ndescription: Investigate a failing test\n---\nREPRODUCE_BEFORE_PATCH\n"
    (skill_root / "SKILL.md").write_text(skill_body)
    (skill_root / "reference.md").write_text("FIRST_TEST_RED_THEN_GREEN\n")
    mcp = build_mcp()
    names = {item.name for item in await mcp.list_tools()}
    required = {"environment_get","file_read","file_write","run_shell","skill_list","skill_load","skill_read","session_manage"}
    assert required <= names, f"Missing {sorted(required-names)}"
    report = [{"gate":"Tools discovered","status":"PASS","detail":len(names)}]

    async def call(name, payload):
        _, response = await mcp.call_tool(name, payload)
        return assert_good(response, name)

    listed = await call("skill_list", {})
    names_skills = {item["name"] for item in listed.get("skills",[])}
    assert "independent-debug" in names_skills, listed
    skill = await call("skill_load",{"name":"independent-debug"})
    assert "REPRODUCE_BEFORE_PATCH" in skill.get("content",""),skill
    ref = await call("skill_read",{"name":"independent-debug","path":"reference.md"})
    assert "FIRST_TEST_RED_THEN_GREEN" in ref.get("content",""),ref
    report.append({"gate":"Skill discovery/full body/reference","status":"PASS",
                   "detail":hashlib.sha256(skill_body.encode()).hexdigest()})

    initial = await call("session_manage",{"action":"start","label":"independent-test","objective":"Repair a failing Python test"})
    session_id = initial.get("session_id")
    assert isinstance(session_id,str) and session_id,initial
    await call("session_manage",{"action":"report","session_id":session_id,"summary":"Fixture created","next":"Reproduce failing test"})
    report.append({"gate":"Persistent task created","status":"PASS","detail":"Session id issued"})

    file_before = await call("file_read",{"path":"calc.py"})
    assert "a + b + 1" in json.dumps(file_before),file_before
    command = f"{sys.executable} calc_test.py"
    red = await call("run_shell",{"command":command,"cwd":".","timeout_s":10})
    assert red.get("exit_code")!=0,red
    report.append({"gate":"Real failing Python test","status":"PASS","detail":"Nonzero exit"})

    changed = await call("file_write",{"path":"calc.py","content":"def add(a, b):\n    return a + b\n"})
    green = await call("run_shell",{"command":command,"cwd":".","timeout_s":10})
    assert green.get("exit_code")==0,green
    assert "return a + b\n" in (repo / "calc.py").read_text()
    report.append({"gate":"Real RED-GREEN file edit","status":"PASS","detail":"Exit code 0 after correction"})

    await call("session_manage",{"action":"report","session_id":session_id,"summary":"Repair verified","next":"Review exact evidence"})
    mcp2 = build_mcp()
    _, resumed_raw = await mcp2.call_tool("session_manage",{"action":"resume","session_id":session_id})
    resumed=assert_good(resumed_raw,"session_manage.resume")
    assert "Repair verified" in json.dumps(resumed),resumed
    report.append({"gate":"Resume logical task with fresh MCP object","status":"PASS","detail":"Verified saved summary"})

    outside=root/"outside.txt"; outside.write_text("DONOTMODIFY\n")
    _, escaped = await mcp.call_tool("file_read",{"path":"../outside.txt"})
    assert escaped.get("ok") is not True,escaped
    assert outside.read_text()=="DONOTMODIFY\n"
    report.append({"gate":"Outside-file read blocked","status":"PASS","detail":"Unchanged external file"})

    return report


def main():
    with tempfile.TemporaryDirectory(prefix="public-mcp-candidates-") as tmp:
        try:
            items=asyncio.run(scenario(Path(tmp)))
        except BaseException as error:
            items=locals().get("items",[])
            items.append({"gate":"Candidate integration","status":"FAIL","detail":repr(error)})
        counts={x:sum(item["status"]==x for item in items) for x in ("PASS","FAIL")}
        report={"schema":"public-candidate-check/v1","candidate":"fwerkor/local-shell-mcp",
                "boundary":"Disposable in-process tools only: no OAuth HTTP connection, no production sandbox, no normal-chat plugin invocation",
                "summary":counts,"results":items}
        output=Path(os.environ.get("REPORT_PATH","fwerkor-candidate.json"))
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+"\n")
        for item in items:print(item)
        print(counts)
        return bool(counts["FAIL"])


if __name__=="__main__":
    raise SystemExit(main())
