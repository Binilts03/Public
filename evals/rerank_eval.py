"""H5 decision-stage experiment: CrossEncoder rerank over v2 top-20 vs threshold gate.

Question: does a dedicated rerank stage move the risk-coverage frontier enough
to justify the extra inference dependency? (H5 kill rule)

Method: 100 use-queries (seed 8, disjoint check vs retrieval_eval seed 7 not
required — reported separately), v2 top-20 reranked with
CrossEncoder ms-marco-MiniLM-L6-v2 + same risk penalty. Metrics: R@1/3, MRR,
high-risk-in-top5, added latency p50. Verdict rule: needs roughly >=10pp
coverage at fixed risk or halved risk at comparable coverage (pilot bar).

Run: python evals/rerank_eval.py  (downloads ~90MB once, CPU minutes)
Out: evals/rerank_eval.json
"""
import asyncio
import json
import random
import statistics
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
PEN = {"high-risk/destructive": 0.45, "reversible-write": 0.15}


async def main():
    corpus = json.load(open(ROOT / "corpus" / "corpus.json"))
    by_id = {t["id"]: t for t in corpus}
    pool = [t for t in corpus if t.get("availability") != "disconnected"
            and t.get("effect_class") not in ("native-decoy",)]
    random.seed(8)
    reads = [t for t in pool if t["effect_class"] == "external-read"]
    writes = [t for t in pool if t["effect_class"] == "reversible-write"]
    risks = [t for t in pool if t["effect_class"] == "high-risk/destructive"]
    golds = random.sample(reads, 70) + random.sample(writes, 20) + random.sample(risks, 10)

    from sentence_transformers import CrossEncoder
    ce = CrossEncoder("cross-encoder/ms-marco-MiniLM-L6-v2")

    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "harness" / "gateway" / "server.py")])
    rows, lat = [], []
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            for g in golds:
                q = (" ".join(g.get("when_to_use", []) + g.get("tags", [])) or g["description"])[:500]
                r2 = json.loads((await s.call_tool("search_tools_v2", {"query": q, "max_results": 20})).content[0].text)
                cands = r2["results"]
                ids_v2 = [o["id"] for o in cands[:5]]
                t0 = time.time()
                pairs = [(q, (by_id[i]["match_text"] or by_id[i]["description"])[:512]) for i in [o["id"] for o in cands]]
                scores = ce.predict(pairs, batch_size=32, show_progress_bar=False)
                lat.append(time.time() - t0)
                rr = sorted(zip([float(x) for x in scores], [o["id"] for o in cands]), reverse=True)
                rr = sorted(rr, key=lambda z: z[0] - PEN.get(by_id[z[1]]["effect_class"], 0.3), reverse=True)
                ids_ce = [i for _, i in rr[:5]]
                rows.append({"gold": g["id"],
                             "rank_v2": ids_v2.index(g["id"]) + 1 if g["id"] in ids_v2 else None,
                             "rank_ce": ids_ce.index(g["id"]) + 1 if g["id"] in ids_ce else None,
                             "hr_v2": sum(1 for i in ids_v2 if by_id[i]["effect_class"] == "high-risk/destructive"),
                             "hr_ce": sum(1 for i in ids_ce if by_id[i]["effect_class"] == "high-risk/destructive")})
    def m(col, k):
        return round(sum(1 for x in rows if x[col] is not None and x[col] <= k) / len(rows), 4)
    out = {"n": len(rows),
           "recall@1_v2": m("rank_v2", 1), "recall@1_ce": m("rank_ce", 1),
           "recall@3_v2": m("rank_v2", 3), "recall@3_ce": m("rank_ce", 3),
           "hr_top5_v2": round(sum(1 for x in rows if x["hr_v2"]) / len(rows), 4),
           "hr_top5_ce": round(sum(1 for x in rows if x["hr_ce"]) / len(rows), 4),
           "rerank_latency_p50_s": round(statistics.median(lat), 3),
           "verdict": "rerank adopted only if recall@1_ce - recall@1_v2 >= 0.10 at hr_top5_ce <= hr_top5_v2"}
    json.dump(out, open(ROOT / "evals" / "rerank_eval.json", "w"), indent=1)
    print(json.dumps(out, indent=1))


asyncio.run(main())
