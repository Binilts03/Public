"""Capability gateway (pilot): MCP server over frozen 1k corpus.

Pattern: search_tools (catalog) + get_tool_details (inspect) + call_capability (execute stub).
All calls are DRY-RUN stubs — no external effects. High-risk tools are refused
at the gateway with requires_explicit_intent, independent of model behavior.

Run: python harness/gateway/server.py  (stdio)
Probe: python evals/gateway_probe.py
"""
import json
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[2]
CORPUS = json.load(open(ROOT / "corpus" / "corpus.json"))
BY_ID = {t["id"]: t for t in CORPUS}
CALL_LOG = ROOT / "evals" / "gateway_calls.jsonl"


def _log(event: str, payload: dict) -> None:
    try:
        with open(CALL_LOG, "a") as f:
            f.write(json.dumps({"event": event, **payload}) + "\n")
    except Exception:
        pass

mcp = FastMCP("capability-gateway")


def _score(query: str, tool: dict) -> int:
    qs = set(re.findall(r"[a-z]+", query.lower()))
    blob = ((tool.get("name") or "") + " " + (tool.get("description") or "")).lower()
    ws = set(re.findall(r"[a-z]+", blob))
    return len(qs & ws)


@mcp.tool()
def search_tools(query: str, max_results: int = 5) -> str:
    """Catalog: lexical search over the 1k capability corpus. Returns id/name/effect_class digests only, never schemas."""
    _log("search_tools", {"query": query, "max_results": max_results})
    ranked = sorted(CORPUS, key=lambda t: -_score(query, t))[: max(1, min(20, max_results))]
    out = [
        {"id": t["id"], "name": t["name"], "effect_class": t.get("effect_class"),
         "availability": t.get("availability", "connected"), "digest": t.get("digest")}
        for t in ranked
    ]
    return json.dumps(out)


@mcp.tool()
def get_tool_details(tool_id: str) -> str:
    """Inspect: full typed schema for one capability id (demand-loaded, not prefetched)."""
    _log("get_tool_details", {"tool_id": tool_id})
    t = BY_ID.get(tool_id)
    if not t:
        return json.dumps({"error": "unknown_tool_id", "tool_id": tool_id})
    return json.dumps(t)


@mcp.tool()
def call_capability(tool_id: str, arguments: str = "{}") -> str:
    """Execute (STUB): dry-run receipt only. Refuses high-risk and disconnected tools."""
    _log("call_capability", {"tool_id": tool_id, "arguments": arguments[:500]})
    t = BY_ID.get(tool_id)
    if not t:
        return json.dumps({"ok": False, "error": "unknown_tool_id", "tool_id": tool_id})
    if t.get("availability") == "disconnected":
        return json.dumps({"ok": False, "error": "provider_unavailable", "tool_id": tool_id,
                           "receipt": None, "dry_run": True})
    if t.get("effect_class") == "high-risk/destructive":
        return json.dumps({"ok": False, "error": "requires_explicit_intent", "tool_id": tool_id,
                           "receipt": None, "dry_run": True,
                           "note": "Gateway refuses speculative destructive execution."})
    try:
        args = json.loads(arguments) if arguments else {}
    except Exception:
        return json.dumps({"ok": False, "error": "invalid_arguments_json", "tool_id": tool_id})
    return json.dumps({"ok": True, "tool_id": tool_id, "dry_run": True,
                       "receipt": {"args_echo": args, "effect_class": t.get("effect_class")},
                       "model_view": f"Stub result for {t['name']}: no external effect committed."})


if __name__ == "__main__":
    mcp.run()
