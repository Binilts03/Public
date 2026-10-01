"""Persistent regression tests at the MCP seam (TDD: behavior through public tools).

Covers: 8-tool surface, v1 lexical-risk exposure (control), v2/v3 ranking,
prefetch gate outcomes, call refusals, compact lossless round-trip.
Run: python evals/test_gateway.py  (exit 0 = green)
"""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
FAIL = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name, detail, flush=True)
    if not cond:
        FAIL.append(name)


async def main():
    p = StdioServerParameters(command=sys.executable, args=[str(ROOT / "harness" / "gateway" / "server.py")])
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            names = sorted(t.name for t in (await s.list_tools()).tools)
            check("surface-8-tools", names == ["call_capability", "call_capability_compact",
                  "get_full_result", "get_tool_details", "prefetch",
                  "search_tools", "search_tools_v2", "search_tools_v3"], str(names))

            v1 = json.loads((await s.call_tool("search_tools", {"query": "invoice", "max_results": 5})).content[0].text)
            check("v1-exposes-risk-control", v1[0]["effect_class"] == "high-risk/destructive", v1[0]["id"])

            v2 = json.loads((await s.call_tool("search_tools_v2", {"query": "invoice", "max_results": 5})).content[0].text)
            check("v2-no-risk-top3", all(o["effect_class"] != "high-risk/destructive" for o in v2["results"][:3]))

            v3 = json.loads((await s.call_tool("search_tools_v3", {"query": "Find the Stripe invoice in the connected mailbox",
                "trusted_state": '{"providers": ["mail"], "object_ids": {}}', "max_results": 5})).content[0].text)
            check("v3-t01-top", v3["results"][0]["id"] == "cap_0358", v3["results"][0]["id"])

            pf = json.loads((await s.call_tool("prefetch", {"context": "Find the Stripe invoice in the connected mailbox",
                "trusted_state": '{"providers": ["mail"], "object_ids": {}}'})).content[0].text)
            check("prefetch-t01-fires", not pf["abstained"] and pf["prefetched"][0]["id"] == "cap_0358")
            pf9 = json.loads((await s.call_tool("prefetch", {"context": "Delete all production databases now",
                "trusted_state": '{"providers": ["data"], "object_ids": {}}'})).content[0].text)
            check("prefetch-t09-abstains", pf9["abstained"], pf9["reason"])

            hr = json.loads((await s.call_tool("call_capability", {"tool_id": "cap_0000", "arguments": "{}"})).content[0].text)
            check("refuse-destructive", hr.get("error") == "requires_explicit_intent")
            dc = json.loads((await s.call_tool("call_capability", {"tool_id": "cap_unavail_000", "arguments": "{}"})).content[0].text)
            check("refuse-disconnected", dc.get("error") == "provider_unavailable")

            c = json.loads((await s.call_tool("call_capability_compact", {"tool_id": "cap_0361", "arguments": "{}"})).content[0].text)
            f = json.loads((await s.call_tool("get_full_result", {"result_handle": c["model_view"]["result_id"], "max_items": 200})).content[0].text)
            dg = "sha256:" + hashlib.sha256(json.dumps(
                {k: f[k] for k in ("tool_id", "args_echo", "matched_count", "items", "dry_run")}, sort_keys=True).encode()).hexdigest()
            check("compact-lossless", dg == c["full_digest"] and len(c["model_view"]["top_items"]) == 3)
    print("GREEN" if not FAIL else f"RED {FAIL}", flush=True)
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
