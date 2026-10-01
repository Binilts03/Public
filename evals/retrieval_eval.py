"""Paired Arm A (v1 lexical) vs Arm B (v2 hybrid+risk) retrieval eval — offline, deterministic.

Design (no gold-label mapping needed):
- Known-item: sample 100 connected tools (70 read / 20 write / 10 high-risk, seed 7).
  Two query formulations per gold: DESC (its description) and USE (its when_to_use/tags).
  Metrics: Recall@1/3/5, MRR, high-risk-in-top5 rate (exposure).
- Negatives: 20 no-tool queries (native math, chitchat, unknown gibberish).
  Metric: top-1 score distribution under v2 (abstention calibration input).

Calls the real gateway over MCP (same code path as harnesses).
Run: python evals/retrieval_eval.py
Out: evals/retrieval_eval.json
"""
import asyncio
import json
import random
import statistics
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
NEGATIVES = [
    "What is 12 * 14?", "List files in current directory", "Hello, how are you?",
    "Write a haiku about rain", "What is the capital of France?",
    "Show git status", "Convert 100 USD to EUR", "Explain recursion briefly",
    "xqz blorpt wobble fnord", "asdf qwer zxcv random keys",
    "What time is it?", "Count from 1 to 10", "Define photosynthesis",
    "Is it raining in London?", "Tell me a joke about databases",
    "How many days in February?", "Sort these numbers: 3 1 2",
    "What colour is the sky?", "Ping localhost", "Echo hello world",
]


def recall_at(rank, k):
    return 1.0 if rank is not None and rank <= k else 0.0


async def main():
    corpus = json.load(open(ROOT / "corpus" / "corpus.json"))
    pool = [t for t in corpus if t.get("availability") != "disconnected"
            and t.get("effect_class") not in ("native-decoy",)]
    random.seed(7)
    reads = [t for t in pool if t["effect_class"] == "external-read"]
    writes = [t for t in pool if t["effect_class"] == "reversible-write"]
    risks = [t for t in pool if t["effect_class"] == "high-risk/destructive"]
    golds = (random.sample(reads, 70) + random.sample(writes, 20) + random.sample(risks, 10))
    by_id = {t["id"]: t for t in corpus}

    params = StdioServerParameters(command="python", args=[str(ROOT / "harness" / "gateway" / "server.py")])
    rows = []
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            for g in golds:
                use_q = " ".join(g.get("when_to_use", []) + g.get("tags", [])) or g["description"]
                for kind, q in (("desc", g["description"][:500]), ("use", use_q[:500])):
                    r1 = json.loads((await s.call_tool("search_tools", {"query": q, "max_results": 5})).content[0].text)
                    r2 = json.loads((await s.call_tool("search_tools_v2", {"query": q, "max_results": 5})).content[0].text)
                    ids1 = [h["id"] for h in r1]
                    ids2 = [o["id"] for o in r2["results"]]
                    rank1 = ids1.index(g["id"]) + 1 if g["id"] in ids1 else None
                    rank2 = ids2.index(g["id"]) + 1 if g["id"] in ids2 else None
                    hr1 = sum(1 for i in ids1 if by_id[i]["effect_class"] == "high-risk/destructive")
                    hr2 = sum(1 for i in ids2 if by_id[i]["effect_class"] == "high-risk/destructive")
                    rows.append({"gold": g["id"], "class": g["effect_class"], "kind": kind,
                                 "rank_v1": rank1, "rank_v2": rank2, "hr_v1": hr1, "hr_v2": hr2,
                                 "top1_v2": r2["results"][0]["score"] if r2["results"] else 0})
            neg_scores = []
            for q in NEGATIVES:
                r2 = json.loads((await s.call_tool("search_tools_v2", {"query": q, "max_results": 5})).content[0].text)
                neg_scores.append(r2["results"][0]["score"] if r2["results"] else 0)

    def agg(kind):
        sub = [x for x in rows if x["kind"] == kind]
        m = {}
        for k in (1, 3, 5):
            m[f"recall@{k}_v1"] = round(sum(recall_at(x["rank_v1"], k) for x in sub) / len(sub), 4)
            m[f"recall@{k}_v2"] = round(sum(recall_at(x["rank_v2"], k) for x in sub) / len(sub), 4)
        rr1 = [1 / x["rank_v1"] for x in sub if x["rank_v1"]]
        rr2 = [1 / x["rank_v2"] for x in sub if x["rank_v2"]]
        m["mrr_v1"] = round(sum(rr1) / len(sub), 4)
        m["mrr_v2"] = round(sum(rr2) / len(sub), 4)
        m["hr_top5_rate_v1"] = round(sum(1 for x in sub if x["hr_v1"] > 0) / len(sub), 4)
        m["hr_top5_rate_v2"] = round(sum(1 for x in sub if x["hr_v2"] > 0) / len(sub), 4)
        m["n"] = len(sub)
        return m

    out = {"desc_queries": agg("desc"), "use_queries": agg("use"),
           "neg_top1_v2": {"mean": round(statistics.mean(neg_scores), 4),
                           "max": round(max(neg_scores), 4),
                           "scores": [round(x, 4) for x in neg_scores]},
           "pos_top1_v2_mean": round(statistics.mean([r["top1_v2"] for r in rows]), 4),
           "rows": rows}
    json.dump(out, open(ROOT / "evals" / "retrieval_eval.json", "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))


asyncio.run(main())
