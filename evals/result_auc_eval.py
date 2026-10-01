"""Arm D vs C result-debt eval: scripted 25-step trajectory over the real gateway.

Arm C arm: full payloads inline (what call_capability would cost if stubs were
realistically sized: measured as get_full_result bytes for the same handle).
Arm D arm: compact view inline + on-demand full fetch on 3 deep-scan steps.

Metrics: per-step model-visible tokens (len//4 heuristic, labeled),
cumulative AUC both arms, % reduction, fetch count, digest/lossless checks
(top_items are exact prefixes; every handle resolves; digests match).

Run: python evals/result_auc_eval.py  (no model calls, no cloud spend)
Out: evals/result_auc.json
"""
import asyncio
import hashlib
import json
import random
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
TOKS = lambda s: max(1, len(s) // 4)


async def main():
    corpus = json.load(open(ROOT / "corpus" / "corpus.json"))
    reads = [t for t in corpus if t.get("effect_class") == "external-read"
             and t.get("availability") != "disconnected"][:8]
    random.seed(11)
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "harness" / "gateway" / "server.py")])
    steps, auc_c, auc_d, fetches, checks = [], 0, 0, 0, []
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            # steps 1-24: search -> details -> compact call for each of 8 tools
            for idx, t in enumerate(reads):
                q = (t.get("tags") or ["data"])[0] + " records"
                r1 = (await s.call_tool("search_tools_v2", {"query": q, "max_results": 5})).content[0].text
                r2 = (await s.call_tool("get_tool_details", {"tool_id": t["id"]})).content[0].text
                r3 = (await s.call_tool("call_capability_compact", {"tool_id": t["id"], "arguments": "{}"})).content[0].text
                v = json.loads(r3)
                full = json.loads((await s.call_tool("get_full_result",
                    {"result_handle": v["model_view"]["result_id"], "max_items": 200})).content[0].text)
                # lossless checks: digest match, prefix exactness
                dg = "sha256:" + hashlib.sha256(json.dumps(
                    {k: full[k] for k in ("tool_id", "args_echo", "matched_count", "items", "dry_run")},
                    sort_keys=True).encode()).hexdigest()
                checks.append(dg == v["full_digest"] and
                              [i["id"] for i in v["model_view"]["top_items"]] ==
                              [i["id"] for i in full["items"][:3]] and
                              all(len(i["snippet"]) <= 200 for i in v["model_view"]["top_items"]))
                deep = idx in (1, 4, 6)  # 3 deep-scan steps fetch full rows
                c_full, c_compact = TOKS(json.dumps(full)), TOKS(r3)
                c_search, c_det = TOKS(r1), TOKS(r2)
                auc_c += c_search + c_det + c_full
                auc_d += c_search + c_det + c_compact + (c_full if deep else 0)
                fetches += 1 if deep else 0
                steps.append({"tool": t["id"], "deep": deep, "c_full": c_full,
                              "c_compact": c_compact, "c_search": c_search, "c_det": c_det})
            # step 25: destructive refusal (small both arms)
            r4 = (await s.call_tool("call_capability_compact",
                {"tool_id": "cap_0000", "arguments": "{}"})).content[0].text
            auc_c += TOKS(r4)
            auc_d += TOKS(r4)
    out = {"steps": steps, "auc_full_inline_C": auc_c, "auc_compact_D": auc_d,
           "reduction": round(1 - auc_d / auc_c, 4), "deep_fetches": fetches,
           "lossless_checks_pass": sum(checks), "lossless_checks_total": len(checks),
           "token_heuristic": "len//4", "full_bytes_per_call": steps[0]["c_full"] * 4 if steps else 0}
    json.dump(out, open(ROOT / "evals" / "result_auc.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "steps"}, indent=1))


asyncio.run(main())
