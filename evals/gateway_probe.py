"""Probe gateway over stdio: tools/list + search + details + stub call + refusal paths."""
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "harness" / "gateway" / "server.py"


async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            tools = await s.list_tools()
            names = [t.name for t in tools.tools]
            print("tools:", names)
            assert {"search_tools", "get_tool_details", "call_capability"} <= set(names), names
            r = await s.call_tool("search_tools", {"query": "find Stripe invoice in mailbox", "max_results": 3})
            print("search:", r.content[0].text[:300])
            first = json.loads(r.content[0].text)[0]
            d = await s.call_tool("get_tool_details", {"tool_id": first["id"]})
            print("details_keys:", sorted(json.loads(d.content[0].text).keys()))
            c = await s.call_tool("call_capability", {"tool_id": first["id"], "arguments": "{}"})
            print("call:", c.content[0].text[:200])
            # refusal paths: pick any high-risk + disconnected ids from corpus
            corpus = json.load(open(ROOT / "corpus" / "corpus.json"))
            hr = next(t for t in corpus if t.get("effect_class") == "high-risk/destructive")
            dc = next(t for t in corpus if t.get("availability") == "disconnected")
            rh = await s.call_tool("call_capability", {"tool_id": hr["id"], "arguments": "{}"})
            rd = await s.call_tool("call_capability", {"tool_id": dc["id"], "arguments": "{}"})
            print("refuse_high_risk:", rh.content[0].text[:160])
            print("refuse_disconnected:", rd.content[0].text[:160])
            assert "requires_explicit_intent" in rh.content[0].text
            assert "provider_unavailable" in rd.content[0].text
            print("PROBE PASS")


asyncio.run(main())
