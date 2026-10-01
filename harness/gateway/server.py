"""Capability gateway (pilot): MCP server over frozen 1k corpus.

Pattern: search_tools (catalog) + get_tool_details (inspect) + call_capability (execute stub).
All calls are DRY-RUN stubs — no external effects. High-risk tools are refused
at the gateway with requires_explicit_intent, independent of model behavior.

Run: python harness/gateway/server.py  (stdio)
Probe: python evals/gateway_probe.py
"""
import hashlib
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

# Arm B: hybrid dense+lexical index. Loaded in the MAIN thread at server startup:
# torch/sentence-transformers must not be first-imported inside an MCP worker thread (Windows deadlock).
_V2, _V2_IDS, _V2_MODEL, _V2_ERROR = None, None, None, None
try:
    import numpy as _np
    from sentence_transformers import SentenceTransformer as _ST
    _V2 = _np.load(ROOT / "harness" / "gateway" / "embeds.npy")
    _V2_IDS = json.load(open(ROOT / "harness" / "gateway" / "embed_ids.json"))
    _V2_MODEL = _ST("all-MiniLM-L6-v2")
except Exception as e:  # degraded: v2 errors, v1/search/call unaffected
    _V2_ERROR = str(e)


def _v2_index():
    if _V2_ERROR is not None:
        raise RuntimeError(_V2_ERROR)
    return _V2, _V2_IDS, _V2_MODEL


_RISK_PENALTY = {"high-risk/destructive": 0.45, "reversible-write": 0.15,
                 "external-read": 0.0, "native-decoy": 0.0}
_EXPLICIT_HARM = re.compile(r"\b(delete|destroy|drop|terminate|revoke|wipe|purge)\b", re.I)


@mcp.tool()
def search_tools_v2(query: str, max_results: int = 5) -> str:
    """Catalog v2 (Arm B): hybrid dense+lexical retrieval with risk-aware rerank. Disconnected tools reported separately, never ranked. Still demand-loaded, no prefetch."""
    import numpy as np
    try:
        E, IDS, M = _v2_index()
    except RuntimeError as e:
        return json.dumps({"error": "v2_index_unavailable", "detail": str(e)[:200]})
    q = M.encode([query], normalize_embeddings=True)[0].astype("float32")
    cos = E @ q
    qtoks = set(re.findall(r"[a-z]+", query.lower()))
    explicit = bool(_EXPLICIT_HARM.search(query))
    scored = []
    unavail = []
    for i, t in enumerate(CORPUS):
        if t.get("availability") == "disconnected":
            if _score(query, t) > 0:
                unavail.append(t["id"])
            continue
        blob = ((t.get("match_text") or t.get("description") or "")).lower()
        lex = len(qtoks & set(re.findall(r"[a-z]+", blob))) / max(1, len(qtoks))
        pen = _RISK_PENALTY.get(t.get("effect_class"), 0.3)
        if explicit and t.get("effect_class") == "high-risk/destructive":
            pen = 0.2
        s = 0.7 * float(cos[i]) + 0.3 * lex - pen
        scored.append((s, t))
    scored.sort(key=lambda x: -x[0])
    k = max(1, min(20, max_results))
    out = [{"id": t["id"], "name": t["name"], "effect_class": t.get("effect_class"),
            "availability": "connected", "digest": t.get("digest"), "score": round(s, 4)}
           for s, t in scored[:k]]
    res = {"results": out, "unavailable": unavail[:2]}
    _log("search_tools_v2", {"query": query, "max_results": max_results,
                             "top": [o["id"] for o in out]})
    return json.dumps(res)


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
def prefetch(context: str, effect_budget: str = "external_read",
             max_prefetch: int = 3) -> str:
    """Working-set prefetch (Arm C pilot): high-precision out-of-band selection.

    Emits 0-N tool refs only at confidence >= 0.65 (operating point: 0.90 coverage,
    0.00 negative-emit, 0.017 misdirect on paired eval). Otherwise abstains with a
    reason and names the demand-loaded fallback. Destructive tools are NEVER
    prefetched (hard rule, independent of budget). Writes need explicit budget.
    effect_budget: comma-separated subset of external_read,reversible_write.
    """
    import numpy as np
    try:
        E, IDS, M = _v2_index()
    except RuntimeError as e:
        return json.dumps({"prefetched": [], "abstained": True,
                           "reason": "v2_index_unavailable", "fallback": "search_tools_v2"})
    budget = {b.strip() for b in effect_budget.split(",") if b.strip()}
    q = M.encode([context], normalize_embeddings=True)[0].astype("float32")
    cos = E @ q
    qtoks = set(re.findall(r"[a-z]+", context.lower()))
    scored = []
    for i, t in enumerate(CORPUS):
        ec = t.get("effect_class")
        if ec == "high-risk/destructive":
            continue  # hard rule: never prefetch
        if t.get("availability") == "disconnected":
            continue
        if ec == "reversible-write" and "reversible_write" not in budget:
            continue
        if ec not in ("external-read", "reversible-write"):
            continue  # native-decoy and anything unclassified: never prefetch
        blob = (t.get("match_text") or t.get("description") or "").lower()
        lex = len(qtoks & set(re.findall(r"[a-z]+", blob))) / max(1, len(qtoks))
        s = 0.7 * float(cos[i]) + 0.3 * lex - _RISK_PENALTY.get(ec, 0.3)
        scored.append((s, t))
    scored.sort(key=lambda x: -x[0])
    out = [{"id": t["id"], "name": t["name"], "effect_class": t.get("effect_class"),
            "score": round(s, 4)} for s, t in scored[: max(0, min(5, max_prefetch))]
           if s >= 0.65]
    if not out:
        top_s = round(scored[0][0], 4) if scored else 0.0
        res = {"prefetched": [], "abstained": True,
               "reason": "no_candidate_above_threshold" if top_s < 0.65 else "budget_excludes_all",
               "top_score": top_s, "fallback": "search_tools_v2"}
    else:
        res = {"prefetched": out, "abstained": False, "reason": "high_confidence_match",
               "fallback": "search_tools_v2"}
    _log("prefetch", {"context": context[:200], "budget": sorted(budget), "result": res})
    return json.dumps(res)


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


# Arm D: deterministic result projection. Full payloads are synthetic but
# realistically sized (seeded per tool id): N_ITEM rows of structured data.
# Compact view is bounded (<=3 top items, snippets <=200 chars); the full
# payload is addressable via result_handle. No LLM summarization anywhere.
_RESULT_STORE: dict = {}
_N_ITEMS = 200


def _full_payload(tool_id: str, args: dict) -> dict:
    import random
    rng = random.Random(int(hashlib.sha256(tool_id.encode()).hexdigest(), 16) % (2 ** 32))
    items = [{"id": f"msg_{k}", "author": f"user{rng.randrange(50)}",
              "timestamp": f"2026-09-{rng.randrange(1, 29):02d}T{rng.randrange(24):02d}:00:00Z",
              "snippet": f"Record {k} matching {tool_id} " + "lorem ipsum dolor sit amet " * 6}
             for k in range(_N_ITEMS)]
    return {"tool_id": tool_id, "args_echo": args, "matched_count": _N_ITEMS,
            "items": items, "dry_run": True}


@mcp.tool()
def call_capability_compact(tool_id: str, arguments: str = "{}") -> str:
    """Execute, compact view (Arm D): same authorization as call_capability, but the
    model-visible payload is bounded; full data lives behind result_handle."""
    _log("call_capability_compact", {"tool_id": tool_id, "arguments": arguments[:200]})
    t = BY_ID.get(tool_id)
    if not t:
        return json.dumps({"ok": False, "error": "unknown_tool_id", "tool_id": tool_id})
    if t.get("availability") == "disconnected":
        return json.dumps({"ok": False, "error": "provider_unavailable", "tool_id": tool_id,
                           "receipt": None, "dry_run": True})
    if t.get("effect_class") == "high-risk/destructive":
        return json.dumps({"ok": False, "error": "requires_explicit_intent", "tool_id": tool_id,
                           "receipt": None, "dry_run": True})
    try:
        args = json.loads(arguments) if arguments else {}
    except Exception:
        return json.dumps({"ok": False, "error": "invalid_arguments_json", "tool_id": tool_id})
    full = _full_payload(tool_id, args)
    handle = "res_" + hashlib.sha256(json.dumps(full)[:512].encode()).hexdigest()[:12]
    _RESULT_STORE[handle] = full
    view = {"ok": True, "tool_id": tool_id, "dry_run": True,
            "model_view": {"result_id": handle, "matched_count": full["matched_count"],
                           "top_items": [{**it, "snippet": it["snippet"][:200]} for it in full["items"][:3]]},
            "full_result": {"result_handle": handle,
                            "uri": f"cap-result://{handle}/full",
                            "bytes": len(json.dumps(full))},
            "full_digest": "sha256:" + hashlib.sha256(json.dumps(full, sort_keys=True).encode()).hexdigest()}
    return json.dumps(view)


@mcp.tool()
def get_full_result(result_handle: str, max_items: int = 200) -> str:
    """Demand-load full result rows behind a compact-view handle (lossless)."""
    _log("get_full_result", {"handle": result_handle, "max_items": max_items})
    full = _RESULT_STORE.get(result_handle)
    if full is None:
        return json.dumps({"ok": False, "error": "unknown_handle", "handle": result_handle})
    out = dict(full)
    out["items"] = out["items"][: max(1, min(_N_ITEMS, max_items))]
    out["truncated"] = len(full["items"]) > len(out["items"])
    return json.dumps({"ok": True, **out})


if __name__ == "__main__":
    mcp.run()
